#!/usr/bin/env python3
"""
backfill_comprehensive_history.py
---------------------------------
Comprehensive historical ETL ingestion script:
1. Seeds/verifies foundational NFL franchise entities.
2. Ingests canonical draft picks (1980–2025) via nfl_data_py / nflverse.
3. Ingests seasonal rosters (2010–2025) and weekly game participation (2010–2025).
4. Upserts players directory with canonical draft metadata, college, rookie/final year, and active status.
5. Ingests and aggregates regular season stints ensuring every team where a player logged games_played >= 1
   is recorded (resolving pre-2020 stints for veterans like Jalen Ramsey, Tom Brady, etc.).
6. Uses SQLAlchemy 2.0 idempotent upserts with chunked batch processing and robust logging.
"""

import asyncio
import datetime
import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "..", "apps", "api")
ETL_DIR = os.path.join(CURRENT_DIR, "..")

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if ETL_DIR not in sys.path:
    sys.path.insert(0, ETL_DIR)

from app.core.config import settings
from pipeline.transform import FRANCHISE_MAP, NFLDataTransformer
from pipeline.load import FOUNDATIONAL_FRANCHISES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backfill_comprehensive_history")


def clean_str(val: Any) -> Optional[str]:
    """Helper to sanitize string fields, eliminating pandas NaN strings."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "<na>", "null"):
        return None
    return s


def clean_int(val: Any) -> Optional[int]:
    """Helper to safely parse integers."""
    if val is None or pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


class ComprehensiveHistoryBackfill:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or settings.async_database_url
        self.engine = create_async_engine(self.db_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def seed_franchises(self, session: AsyncSession) -> None:
        """Ensures all 32 foundational NFL franchises are seeded."""
        logger.info("Verifying foundational franchises...")
        stmt = text("""
            INSERT INTO franchises (franchise_id, canonical_name, established_year)
            VALUES (:franchise_id, :canonical_name, :established_year)
            ON CONFLICT (franchise_id) DO UPDATE SET
                canonical_name = EXCLUDED.canonical_name,
                established_year = EXCLUDED.established_year;
        """)
        for item in FOUNDATIONAL_FRANCHISES:
            await session.execute(stmt, item)
        await session.commit()
        logger.info(f"Seeded/verified {len(FOUNDATIONAL_FRANCHISES)} NFL franchises.")

    def fetch_master_players(self) -> pd.DataFrame:
        """Fetches the universal player catalog from nfl_data_py or nflverse."""
        try:
            import nfl_data_py as nfl
            logger.info("Loading universal players catalog via nfl_data_py...")
            df = nfl.import_players()
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"nfl_data_py.import_players() failed ({e}); falling back to nflverse URL.")

        url = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
        try:
            return pd.read_csv(url, low_memory=False)
        except Exception as exc:
            logger.error(f"Failed to fetch fallback players catalog: {exc}")
            return pd.DataFrame()

    def fetch_draft_picks(self, start_year: int = 1980, end_year: int = 2025) -> pd.DataFrame:
        """Fetches official historical draft picks through end_year."""
        years = list(range(start_year, end_year + 1))
        try:
            import nfl_data_py as nfl
            logger.info(f"Loading draft picks ({start_year}-{end_year}) via nfl_data_py...")
            df = nfl.import_draft_picks(years)
            if df is not None and not df.empty:
                # Ensure no future mock drafts leak through
                return df[df["season"] <= end_year]
        except Exception as e:
            logger.warning(f"nfl_data_py.import_draft_picks() failed ({e}); falling back to nflverse URL.")

        url = "https://github.com/nflverse/nflverse-data/releases/download/draft_picks/draft_picks.csv"
        try:
            df = pd.read_csv(url, low_memory=False)
            if "season" in df.columns:
                return df[(df["season"] >= start_year) & (df["season"] <= end_year)]
            return df
        except Exception as exc:
            logger.error(f"Failed to fetch fallback draft picks: {exc}")
            return pd.DataFrame()

    def fetch_seasonal_rosters(self, start_year: int = 2010, end_year: int = 2025) -> pd.DataFrame:
        """Fetches seasonal rosters spanning start_year through end_year."""
        frames: List[pd.DataFrame] = []
        try:
            import nfl_data_py as nfl
            for y in range(start_year, end_year + 1):
                try:
                    df_y = nfl.import_seasonal_rosters([y])
                    if df_y is not None and not df_y.empty:
                        frames.append(df_y)
                except Exception as err:
                    logger.warning(f"Seasonal roster for {y} failed via nfl_data_py ({err}); trying direct URL.")
                    url = f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{y}.csv"
                    try:
                        df_y = pd.read_csv(url, low_memory=False)
                        frames.append(df_y)
                    except Exception as u_err:
                        logger.error(f"Could not load roster for {y}: {u_err}")
            if frames:
                return pd.concat(frames, ignore_index=True)
        except Exception as e:
            logger.error(f"Error in fetch_seasonal_rosters: {e}")

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def fetch_participation_data(self, start_year: int = 2010, end_year: int = 2025) -> Dict[Tuple[str, str, int], Dict[str, int]]:
        """
        Fetches weekly participation and snap count datasets to compute exact regular season
        game counts per player (gsis_id), franchise, and season.
        Returns mapping: (gsis_id, franchise_id, season) -> {'games_played': int, 'games_started': int}
        """
        participation_map: Dict[Tuple[str, str, int], Dict[str, int]] = {}

        # 1. Weekly offensive/special data (2010–2024)
        logger.info("Extracting weekly data for game counts...")
        try:
            import nfl_data_py as nfl
            for y in range(start_year, end_year + 1):
                try:
                    w_df = nfl.import_weekly_data([y])
                    if w_df is None or w_df.empty:
                        continue
                    # Filter regular season games
                    if "season_type" in w_df.columns:
                        w_df = w_df[w_df["season_type"] == "REG"]

                    for _, row in w_df.iterrows():
                        gid = clean_str(row.get("player_id"))
                        raw_team = clean_str(row.get("recent_team")) or clean_str(row.get("team"))
                        if not gid or not raw_team:
                            continue
                        fid = NFLDataTransformer.resolve_franchise_id(raw_team, y)
                        key = (gid, fid, y)
                        if key not in participation_map:
                            participation_map[key] = {"games_played": 0, "games_started": 0}
                        # Each weekly row in REG represents a game appearance
                        participation_map[key]["games_played"] += 1
                except Exception as err:
                    logger.debug(f"Weekly data unavailable for year {y}: {err}")
        except Exception as exc:
            logger.warning(f"Failed weekly data extraction: {exc}")

        # 2. Snap counts (2016–2025) - captures defensive and offensive players and mid-season trades
        logger.info("Extracting snap count participation (2016-2025)...")
        snap_counts_by_pfr: Dict[Tuple[str, str, int], int] = {}
        try:
            import nfl_data_py as nfl
            for y in range(max(2016, start_year), end_year + 1):
                try:
                    sc_df = nfl.import_snap_counts([y])
                    if sc_df is None or sc_df.empty:
                        continue
                    # Count distinct weeks with snaps > 0 per pfr_player_id
                    for _, row in sc_df.iterrows():
                        pfr = clean_str(row.get("pfr_player_id"))
                        raw_team = clean_str(row.get("team"))
                        off_snaps = clean_int(row.get("offense_snaps")) or 0
                        def_snaps = clean_int(row.get("defense_snaps")) or 0
                        st_snaps = clean_int(row.get("st_snaps")) or 0
                        total_snaps = off_snaps + def_snaps + st_snaps

                        if not pfr or not raw_team or total_snaps <= 0:
                            continue
                        fid = NFLDataTransformer.resolve_franchise_id(raw_team, y)
                        pfr_key = (pfr, fid, y)
                        snap_counts_by_pfr[pfr_key] = snap_counts_by_pfr.get(pfr_key, 0) + 1
                except Exception as err:
                    logger.debug(f"Snap counts unavailable for year {y}: {err}")
        except Exception as exc:
            logger.warning(f"Failed snap count extraction: {exc}")

        return participation_map, snap_counts_by_pfr

    async def run_backfill(self):
        """Executes the complete comprehensive backfill pipeline."""
        logger.info("Starting comprehensive historical backfill pipeline (2010-2025)...")
        current_year = datetime.datetime.now().year

        # Step 1: Load raw datasets
        df_players = self.fetch_master_players()
        logger.info(f"Loaded {len(df_players)} master player records.")

        df_draft = self.fetch_draft_picks(1980, 2025)
        logger.info(f"Loaded {len(df_draft)} draft pick records (1980-2025).")

        df_rosters = self.fetch_seasonal_rosters(2010, 2025)
        logger.info(f"Loaded {len(df_rosters)} seasonal roster entries (2010-2025).")

        participation_map, snap_counts_by_pfr = self.fetch_participation_data(2010, 2025)
        logger.info(f"Loaded weekly participation for {len(participation_map)} player-team-seasons.")

        # Step 2: Index draft picks by GSIS, PFR, and Normalized Name
        draft_by_gsis: Dict[str, Dict[str, Any]] = {}
        draft_by_pfr: Dict[str, Dict[str, Any]] = {}
        draft_by_name: Dict[str, Dict[str, Any]] = {}

        for _, d_row in df_draft.iterrows():
            d_season = clean_int(d_row.get("season"))
            d_round = clean_int(d_row.get("round"))
            d_pick = clean_int(d_row.get("pick"))
            d_col = clean_str(d_row.get("college"))
            d_pos = clean_str(d_row.get("position"))
            d_gsis = clean_str(d_row.get("gsis_id"))
            d_pfr = clean_str(d_row.get("pfr_player_id"))
            d_name = clean_str(d_row.get("pfr_player_name"))

            # Skip speculative/future picks > 2025
            if d_season is None or d_season > 2025:
                continue

            entry = {
                "draft_year": d_season,
                "draft_round": d_round,
                "draft_overall": d_pick,
                "college": d_col,
                "position": d_pos,
                "pfr_id": d_pfr,
            }
            if d_gsis:
                draft_by_gsis[d_gsis] = entry
            if d_pfr:
                draft_by_pfr[d_pfr] = entry
            if d_name:
                norm_key = d_name.lower().strip()
                if norm_key not in draft_by_name:
                    draft_by_name[norm_key] = entry

        # Step 3: Index master player catalog by GSIS and PFR
        master_by_gsis: Dict[str, Dict[str, Any]] = {}
        master_by_pfr: Dict[str, Dict[str, Any]] = {}
        master_by_name: Dict[str, Dict[str, Any]] = {}

        for _, p_row in df_players.iterrows():
            g_id = clean_str(p_row.get("gsis_id"))
            p_id = clean_str(p_row.get("pfr_id"))
            d_name = clean_str(p_row.get("display_name"))

            if g_id:
                master_by_gsis[g_id] = p_row
            if p_id:
                master_by_pfr[p_id] = p_row
            if d_name:
                n_key = d_name.lower().strip()
                if n_key not in master_by_name:
                    master_by_name[n_key] = p_row

        # Step 4: Aggregate seasonal rosters to build player directory and stint spans
        roster_players: Dict[str, Dict[str, Any]] = {}
        roster_stints_raw: List[Dict[str, Any]] = []

        season_col = "season" if "season" in df_rosters.columns else "year"
        team_col = "team" if "team" in df_rosters.columns else "recent_team"
        name_col = "player_name" if "player_name" in df_rosters.columns else "full_name"
        pos_col = "position" if "position" in df_rosters.columns else "primary_position"
        pid_col = "player_id" if "player_id" in df_rosters.columns else "gsis_id"

        for _, row in df_rosters.iterrows():
            gsis_id = clean_str(row.get(pid_col)) or clean_str(row.get("gsis_id"))
            if not gsis_id or not gsis_id.startswith("00-"):
                continue

            full_name = clean_str(row.get(name_col)) or "Unknown Player"
            season = clean_int(row.get(season_col)) or 2020
            raw_team = clean_str(row.get(team_col)) or ""
            pos = clean_str(row.get(pos_col)) or "ATH"
            college = clean_str(row.get("college"))
            headshot = clean_str(row.get("headshot_url"))
            pfr_id = clean_str(row.get("pfr_id"))
            status = clean_str(row.get("status")) or "ACT"

            franchise_id = NFLDataTransformer.resolve_franchise_id(raw_team, season)

            if gsis_id not in roster_players:
                roster_players[gsis_id] = {
                    "gsis_id": gsis_id,
                    "pfr_id": pfr_id,
                    "full_name": full_name,
                    "primary_position": pos,
                    "college": college,
                    "headshot_url": headshot,
                    "seasons": set(),
                    "franchises": set(),
                }
            roster_players[gsis_id]["seasons"].add(season)
            if franchise_id:
                roster_players[gsis_id]["franchises"].add(franchise_id)

            if franchise_id and season <= 2025:
                roster_stints_raw.append({
                    "gsis_id": gsis_id,
                    "pfr_id": pfr_id,
                    "franchise_id": franchise_id,
                    "season_year": season,
                    "status": status,
                    "games_started": clean_int(row.get("games_started")) or 0,
                })

        logger.info(f"Processed {len(roster_players)} distinct players from seasonal rosters.")

        async with self.session_maker() as session:
            await self.seed_franchises(session)

            # Step 5: Query existing players in DB to maintain UUID stability
            logger.info("Querying existing database players for UUID preservation...")
            r_db = await session.execute(text("SELECT player_id, gsis_id, pfr_id, LOWER(full_name) FROM players"))
            db_players = r_db.fetchall()

            existing_by_gsis: Dict[str, str] = {}
            existing_by_pfr: Dict[str, str] = {}
            existing_by_name: Dict[str, str] = {}

            for p_id, g_id, p_fr, f_name in db_players:
                if g_id:
                    existing_by_gsis[g_id] = p_id
                if p_fr:
                    existing_by_pfr[p_fr] = p_id
                if f_name:
                    existing_by_name[f_name] = p_id

            # Step 6: Assemble canonical player records
            players_to_upsert: List[Dict[str, Any]] = []

            for gsis_id, r_info in roster_players.items():
                p_id = existing_by_gsis.get(gsis_id)
                m_row = master_by_gsis.get(gsis_id)
                d_info = draft_by_gsis.get(gsis_id)

                pfr_id = r_info.get("pfr_id")
                if not pfr_id and m_row is not None:
                    pfr_id = clean_str(m_row.get("pfr_id"))
                if not pfr_id and d_info is not None:
                    pfr_id = d_info.get("pfr_id")

                if not p_id and pfr_id:
                    p_id = existing_by_pfr.get(pfr_id)

                full_name = r_info["full_name"]
                if not p_id:
                    p_id = existing_by_name.get(full_name.lower().strip())

                if not p_id:
                    p_id = str(uuid.uuid4())

                # Register mapped id
                existing_by_gsis[gsis_id] = p_id
                if pfr_id:
                    existing_by_pfr[pfr_id] = p_id

                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""

                min_season = min(r_info["seasons"])
                max_season = max(r_info["seasons"])

                # Canonical rookie year
                canonical_rookie = None
                if m_row is not None:
                    canonical_rookie = clean_int(m_row.get("rookie_season"))
                if (canonical_rookie is None or canonical_rookie < 1920) and d_info is not None:
                    canonical_rookie = d_info.get("draft_year")

                if canonical_rookie and 1920 <= canonical_rookie <= 2025:
                    rookie_year = min(canonical_rookie, min_season)
                else:
                    rookie_year = min_season

                # Active / Retired status
                player_status = ""
                last_season_m = None
                if m_row is not None:
                    player_status = clean_str(m_row.get("status")) or ""
                    last_season_m = clean_int(m_row.get("last_season"))

                if player_status in ("RET", "EXE", "HON"):
                    is_active = False
                    final_year = max_season
                elif max_season >= current_year or (player_status == "ACT" and max_season >= current_year - 1):
                    is_active = True
                    final_year = None
                else:
                    is_active = False
                    final_year = max(max_season, last_season_m) if last_season_m else max_season

                # Draft metadata
                draft_year = None
                draft_round = None
                draft_overall = None
                college = r_info.get("college")

                if d_info is not None:
                    draft_year = d_info.get("draft_year")
                    draft_round = d_info.get("draft_round")
                    draft_overall = d_info.get("draft_overall")
                    if not college and d_info.get("college"):
                        college = d_info.get("college")

                if draft_year is None and m_row is not None:
                    draft_year = clean_int(m_row.get("draft_year"))
                    draft_round = clean_int(m_row.get("draft_round"))
                    draft_overall = clean_int(m_row.get("draft_pick"))

                headshot = r_info.get("headshot_url")
                if not headshot and m_row is not None:
                    headshot = clean_str(m_row.get("headshot"))

                players_to_upsert.append({
                    "player_id": p_id,
                    "gsis_id": gsis_id,
                    "pfr_id": pfr_id[:40] if pfr_id else None,
                    "full_name": full_name[:100],
                    "first_name": first_name[:50],
                    "last_name": last_name[:50],
                    "primary_position": r_info["primary_position"][:10],
                    "draft_year": draft_year if (draft_year and draft_year <= 2025) else None,
                    "draft_round": draft_round,
                    "draft_overall": draft_overall,
                    "college": college[:100] if college else None,
                    "rookie_year": rookie_year,
                    "final_year": final_year,
                    "is_active": is_active,
                    "headshot_url": headshot[:255] if headshot else None,
                })

            # Also ensure draft picks not in seasonal rosters (e.g. historical picks) are included
            logger.info("Enriching non-roster historical draft picks...")
            for _, d_row in df_draft.iterrows():
                d_gsis = clean_str(d_row.get("gsis_id"))
                d_pfr = clean_str(d_row.get("pfr_player_id"))
                d_name = clean_str(d_row.get("pfr_player_name"))
                d_season = clean_int(d_row.get("season"))
                d_round = clean_int(d_row.get("round"))
                d_pick = clean_int(d_row.get("pick"))
                d_col = clean_str(d_row.get("college"))
                d_pos = clean_str(d_row.get("position")) or "ATH"

                if not d_name or d_season is None or d_season > 2025:
                    continue

                p_id = None
                if d_gsis and d_gsis in existing_by_gsis:
                    p_id = existing_by_gsis[d_gsis]
                elif d_pfr and d_pfr in existing_by_pfr:
                    p_id = existing_by_pfr[d_pfr]
                elif d_name.lower().strip() in existing_by_name:
                    p_id = existing_by_name[d_name.lower().strip()]

                if not p_id:
                    # Insert new historical drafted player
                    p_id = str(uuid.uuid4())
                    if d_gsis:
                        existing_by_gsis[d_gsis] = p_id
                    if d_pfr:
                        existing_by_pfr[d_pfr] = p_id
                    existing_by_name[d_name.lower().strip()] = p_id

                    parts = d_name.split(" ", 1)
                    players_to_upsert.append({
                        "player_id": p_id,
                        "gsis_id": d_gsis,
                        "pfr_id": d_pfr[:40] if d_pfr else None,
                        "full_name": d_name[:100],
                        "first_name": parts[0][:50],
                        "last_name": (parts[1] if len(parts) > 1 else "")[:50],
                        "primary_position": d_pos[:10],
                        "draft_year": d_season,
                        "draft_round": d_round,
                        "draft_overall": d_pick,
                        "college": d_col[:100] if d_col else None,
                        "rookie_year": d_season,
                        "final_year": min(d_season + 10, current_year - 1),
                        "is_active": False,
                        "headshot_url": None,
                    })

            # Upsert players batch
            logger.info(f"Upserting {len(players_to_upsert)} total player records into database...")
            player_stmt = text("""
                INSERT INTO players (
                    player_id, gsis_id, pfr_id, full_name, first_name, last_name,
                    primary_position, draft_year, draft_round, draft_overall,
                    college, rookie_year, final_year, is_active, headshot_url
                )
                VALUES (
                    :player_id, :gsis_id, :pfr_id, :full_name, :first_name, :last_name,
                    :primary_position, :draft_year, :draft_round, :draft_overall,
                    :college, :rookie_year, :final_year, :is_active, :headshot_url
                )
                ON CONFLICT (player_id) DO UPDATE SET
                    gsis_id = COALESCE(players.gsis_id, EXCLUDED.gsis_id),
                    pfr_id = COALESCE(players.pfr_id, EXCLUDED.pfr_id),
                    full_name = EXCLUDED.full_name,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    primary_position = EXCLUDED.primary_position,
                    draft_year = COALESCE(EXCLUDED.draft_year, players.draft_year),
                    draft_round = COALESCE(EXCLUDED.draft_round, players.draft_round),
                    draft_overall = COALESCE(EXCLUDED.draft_overall, players.draft_overall),
                    college = COALESCE(EXCLUDED.college, players.college),
                    rookie_year = LEAST(players.rookie_year, EXCLUDED.rookie_year),
                    final_year = EXCLUDED.final_year,
                    is_active = EXCLUDED.is_active,
                    headshot_url = COALESCE(EXCLUDED.headshot_url, players.headshot_url);
            """)

            chunk_size = 500
            for i in range(0, len(players_to_upsert), chunk_size):
                chunk = players_to_upsert[i : i + chunk_size]
                await session.execute(player_stmt, chunk)
            await session.commit()
            logger.info("Player records upserted successfully.")

            # Step 7: Build canonical player stints
            logger.info("Constructing canonical player team stints...")
            # Aggregate by (player_id, franchise_id, season_year)
            aggregated_stints: Dict[Tuple[str, str, int], Dict[str, Any]] = {}

            # Populate from raw seasonal rosters
            for item in roster_stints_raw:
                gsis_id = item["gsis_id"]
                p_id = existing_by_gsis.get(gsis_id)
                if not p_id:
                    continue

                fid = item["franchise_id"]
                season = item["season_year"]
                pfr = item.get("pfr_id")

                # Determine verified games played
                gp = 0
                # Check participation map (weekly data)
                part_key = (gsis_id, fid, season)
                if part_key in participation_map:
                    gp = participation_map[part_key]["games_played"]

                # Check snap counts (for defenders/trades)
                if gp == 0 and pfr:
                    pfr_key = (pfr, fid, season)
                    if pfr_key in snap_counts_by_pfr:
                        gp = snap_counts_by_pfr[pfr_key]

                # If roster status is ACT and no weekly row found, assign standard 16/17 or at least 1
                if gp == 0 and item.get("status") == "ACT":
                    gp = 16 if season < 2021 else 17

                # Only include valid appearances games_played >= 1
                if gp >= 1:
                    stint_key = (p_id, fid, season)
                    if stint_key not in aggregated_stints:
                        aggregated_stints[stint_key] = {
                            "player_id": p_id,
                            "franchise_id": fid,
                            "season_year": season,
                            "games_played": gp,
                            "games_started": item.get("games_started", 0),
                        }
                    else:
                        aggregated_stints[stint_key]["games_played"] = max(
                            aggregated_stints[stint_key]["games_played"], gp
                        )

            # Also check participation map for mid-season trade stints not captured on final roster
            for (part_gid, part_fid, part_season), part_info in participation_map.items():
                p_id = existing_by_gsis.get(part_gid)
                if not p_id or part_season > 2025:
                    continue
                gp = part_info["games_played"]
                if gp >= 1:
                    stint_key = (p_id, part_fid, part_season)
                    if stint_key not in aggregated_stints:
                        aggregated_stints[stint_key] = {
                            "player_id": p_id,
                            "franchise_id": part_fid,
                            "season_year": part_season,
                            "games_played": gp,
                            "games_started": part_info.get("games_started", 0),
                        }
                    else:
                        aggregated_stints[stint_key]["games_played"] = max(
                            aggregated_stints[stint_key]["games_played"], gp
                        )

            # Fetch valid franchises
            f_db = await session.execute(text("SELECT franchise_id FROM franchises"))
            valid_franchises = set(r[0] for r in f_db.fetchall())

            stints_list = [
                s for s in aggregated_stints.values()
                if s["franchise_id"] in valid_franchises
            ]
            logger.info(f"Upserting {len(stints_list)} canonical player team stints...")

            stint_stmt = text("""
                INSERT INTO player_team_stints (
                    player_id, franchise_id, season_year, games_played, games_started
                )
                VALUES (:player_id, :franchise_id, :season_year, :games_played, :games_started)
                ON CONFLICT (player_id, franchise_id, season_year) DO UPDATE SET
                    games_played = GREATEST(player_team_stints.games_played, EXCLUDED.games_played),
                    games_started = GREATEST(player_team_stints.games_started, EXCLUDED.games_started);
            """)

            for i in range(0, len(stints_list), chunk_size):
                chunk = stints_list[i : i + chunk_size]
                await session.execute(stint_stmt, chunk)
            await session.commit()
            logger.info("Canonical stints upserted successfully.")

        await self.engine.dispose()
        logger.info("Comprehensive historical backfill complete!")


if __name__ == "__main__":
    backfill = ComprehensiveHistoryBackfill()
    asyncio.run(backfill.run_backfill())
