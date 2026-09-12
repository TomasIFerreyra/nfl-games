#!/usr/bin/env python3
"""
sync_2025_2026.py
------------------
Principal Data Pipeline for Season 2025 Backfill & 2026 Active Roster Sync:
1. Seeds 2025 & 2026 team_seasons across all foundational NFL franchises.
2. Ingests 2025 regular season statistics into player_season_stats and updates player_team_stints.
3. Ingests 2026 opening-week rosters (including rookie draft class, active rosters, and trades e.g. A.J. Brown -> NE).
4. Recomputes player_career_stats aggregations.
"""

import asyncio
import datetime
import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "..", "apps", "api")
ETL_DIR = CURRENT_DIR

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
logger = logging.getLogger("sync_2025_2026")


def clean_str(val: Any) -> Optional[str]:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "<na>", "null"):
        return None
    return s


def clean_int(val: Any) -> Optional[int]:
    if val is None or pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def clean_float(val: Any) -> float:
    if val is None or pd.isna(val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


TEAM_NAME_MAP: Dict[str, str] = {
    "ARI": "Arizona Cardinals",
    "ATL": "Atlanta Falcons",
    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",
    "DET": "Detroit Lions",
    "GNB": "Green Bay Packers",
    "GB":  "Green Bay Packers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "JAC": "Jacksonville Jaguars",
    "KC":  "Kansas City Chiefs",
    "KAN": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams",
    "LA":  "Los Angeles Rams",
    "LVR": "Las Vegas Raiders",
    "LV":  "Las Vegas Raiders",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NWE": "New England Patriots",
    "NE":  "New England Patriots",
    "NOR": "New Orleans Saints",
    "NO":  "New Orleans Saints",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "SFO": "San Francisco 49ers",
    "SF":  "San Francisco 49ers",
    "TAM": "Tampa Bay Buccaneers",
    "TB":  "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",
    "WAS": "Washington Commanders",
    "WSH": "Washington Commanders",
}


async def seed_team_seasons(session: AsyncSession, years: List[int]) -> None:
    """
    Ensures all 32 foundational NFL franchises have team_seasons records for given years.
    """
    logger.info(f"Seeding team_seasons for years {years}...")
    
    # First make sure foundational franchises exist
    stmt_f = text("""
        INSERT INTO franchises (franchise_id, canonical_name, established_year)
        VALUES (:franchise_id, :canonical_name, :established_year)
        ON CONFLICT (franchise_id) DO UPDATE SET
            canonical_name = EXCLUDED.canonical_name,
            established_year = EXCLUDED.established_year;
    """)
    await session.execute(stmt_f, FOUNDATIONAL_FRANCHISES)
    await session.commit()

    ts_records = []
    for yr in years:
        for f in FOUNDATIONAL_FRANCHISES:
            f_id = f["franchise_id"]
            c_name = f["canonical_name"]
            ts_id = f"{f_id}_{yr}"
            ts_records.append({
                "team_season_id": ts_id,
                "franchise_id": f_id,
                "season_year": yr,
                "team_name": c_name,
                "team_abbr": f_id,
            })

    stmt_ts = text("""
        INSERT INTO team_seasons (team_season_id, franchise_id, season_year, team_name, team_abbr)
        VALUES (:team_season_id, :franchise_id, :season_year, :team_name, :team_abbr)
        ON CONFLICT (team_season_id) DO UPDATE SET
            franchise_id = EXCLUDED.franchise_id,
            season_year = EXCLUDED.season_year,
            team_name = EXCLUDED.team_name,
            team_abbr = EXCLUDED.team_abbr;
    """)
    for i in range(0, len(ts_records), 500):
        await session.execute(stmt_ts, ts_records[i : i + 500])
    await session.commit()
    logger.info(f"Seeded {len(ts_records)} team_seasons records.")


def fetch_2025_stats() -> pd.DataFrame:
    """
    Fetches 2025 regular season player stats from nflverse.
    """
    url = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_2025.csv"
    try:
        logger.info(f"Downloading 2025 player stats from {url}...")
        df = pd.read_csv(url, low_memory=False)
        logger.info(f"Loaded 2025 stats: {len(df)} rows.")
        return df
    except Exception as e:
        logger.warning(f"Direct download of stats_player_reg_2025 failed: {e}. Attempting fallback...")
        try:
            import nfl_data_py as nfl
            df = nfl.import_seasonal_pfr("pass", [2025])
            return df
        except Exception as e2:
            logger.error(f"Fallback 2025 stats extraction failed: {e2}")
            return pd.DataFrame()


def fetch_rosters(year: int) -> pd.DataFrame:
    """
    Fetches seasonal rosters for a given year.
    """
    url = f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{year}.csv"
    try:
        logger.info(f"Downloading {year} rosters from {url}...")
        df = pd.read_csv(url, low_memory=False)
        logger.info(f"Loaded {year} rosters: {len(df)} rows.")
        return df
    except Exception as e:
        logger.warning(f"Direct download of roster_{year}.csv failed: {e}. Attempting nfl_data_py...")
        try:
            import nfl_data_py as nfl
            df = nfl.import_seasonal_rosters([year])
            return df
        except Exception as e2:
            logger.error(f"nfl_data_py import_seasonal_rosters({year}) failed: {e2}")
            return pd.DataFrame()


def fetch_weekly_rosters(year: int) -> pd.DataFrame:
    """
    Fetches weekly rosters for a given year.
    """
    url = f"https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{year}.csv"
    try:
        logger.info(f"Downloading {year} weekly rosters from {url}...")
        df = pd.read_csv(url, low_memory=False)
        logger.info(f"Loaded {year} weekly rosters: {len(df)} rows.")
        return df
    except Exception as e:
        logger.warning(f"Direct download of roster_weekly_{year}.csv failed: {e}.")
        return pd.DataFrame()


async def sync_2025_season(session: AsyncSession) -> Tuple[int, int, int]:
    """
    Ingests 2025 player metadata, stats into player_season_stats, and appearances into player_team_stints.
    """
    logger.info("=== Starting 2025 Season Ingestion ===")
    
    # 1. Roster extraction
    rosters_2025 = fetch_rosters(2025)
    stats_2025 = fetch_2025_stats()

    # Load existing player mapping: gsis_id -> player_id, pfr_id -> player_id, name -> player_id
    res = await session.execute(text("SELECT player_id, gsis_id, pfr_id, full_name FROM players;"))
    rows = res.fetchall()
    player_id_by_gsis = {r[1]: r[0] for r in rows if r[1]}
    player_id_by_pfr = {r[2]: r[0] for r in rows if r[2]}
    player_id_by_name = {r[3].lower(): r[0] for r in rows if r[3]}

    players_upserted = 0
    # Batch upsert players from 2025 roster
    if not rosters_2025.empty:
        name_col = "full_name" if "full_name" in rosters_2025.columns else "player_name"
        player_records = []
        seen_pids = set()

        for _, row in rosters_2025.iterrows():
            gsis_id = clean_str(row.get("gsis_id") or row.get("player_id"))
            pfr_id = clean_str(row.get("pfr_id"))
            full_name = clean_str(row.get(name_col))
            if not full_name:
                continue
            
            p_id = None
            if gsis_id and gsis_id in player_id_by_gsis:
                p_id = player_id_by_gsis[gsis_id]
            elif pfr_id and pfr_id in player_id_by_pfr:
                p_id = player_id_by_pfr[pfr_id]
            elif full_name.lower() in player_id_by_name:
                p_id = player_id_by_name[full_name.lower()]

            if not p_id:
                p_id = str(uuid.uuid4())
                if gsis_id:
                    player_id_by_gsis[gsis_id] = p_id
                if pfr_id:
                    player_id_by_pfr[pfr_id] = p_id

            if pfr_id and pfr_id in player_id_by_pfr and player_id_by_pfr[pfr_id] != p_id:
                pfr_id = None
            if gsis_id and gsis_id in player_id_by_gsis and player_id_by_gsis[gsis_id] != p_id:
                gsis_id = None

            if p_id in seen_pids:
                continue
            seen_pids.add(p_id)

            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            pos = clean_str(row.get("position")) or "ATH"
            college = clean_str(row.get("college"))
            headshot = clean_str(row.get("headshot_url"))
            jersey = clean_int(row.get("jersey_number"))
            draft_yr = clean_int(row.get("entry_year") or row.get("rookie_year") or row.get("draft_year"))
            draft_rd = clean_int(row.get("draft_round"))
            draft_num = clean_int(row.get("draft_number"))
            rookie_yr = clean_int(row.get("rookie_year") or row.get("entry_year")) or 2025

            player_records.append({
                "player_id": p_id,
                "gsis_id": gsis_id,
                "pfr_id": pfr_id,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_position": pos[:10],
                "draft_year": draft_yr,
                "draft_round": draft_rd,
                "draft_overall": draft_num,
                "college": college[:100] if college else None,
                "rookie_year": rookie_yr,
                "headshot_url": headshot[:255] if headshot else None,
                "jersey_number": jersey,
            })

        stmt_p2025 = text("""
            INSERT INTO players (
                player_id, gsis_id, pfr_id, full_name, first_name, last_name,
                primary_position, draft_year, draft_round, draft_overall,
                college, rookie_year, final_year, is_active, headshot_url, jersey_number
            )
            VALUES (
                :player_id, :gsis_id, :pfr_id, :full_name, :first_name, :last_name,
                :primary_position, :draft_year, :draft_round, :draft_overall,
                :college, :rookie_year, NULL, true, :headshot_url, :jersey_number
            )
            ON CONFLICT (player_id) DO UPDATE SET
                gsis_id = COALESCE(players.gsis_id, EXCLUDED.gsis_id),
                pfr_id = COALESCE(players.pfr_id, EXCLUDED.pfr_id),
                full_name = EXCLUDED.full_name,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                primary_position = EXCLUDED.primary_position,
                college = COALESCE(players.college, EXCLUDED.college),
                draft_year = COALESCE(players.draft_year, EXCLUDED.draft_year),
                draft_round = COALESCE(players.draft_round, EXCLUDED.draft_round),
                draft_overall = COALESCE(players.draft_overall, EXCLUDED.draft_overall),
                is_active = true,
                final_year = NULL,
                headshot_url = COALESCE(EXCLUDED.headshot_url, players.headshot_url),
                jersey_number = COALESCE(EXCLUDED.jersey_number, players.jersey_number);
        """)
        for i in range(0, len(player_records), 500):
            await session.execute(stmt_p2025, player_records[i : i + 500])
        await session.commit()
        players_upserted = len(player_records)
        logger.info(f"Upserted {players_upserted} players from 2025 rosters.")
        logger.info(f"Upserted {players_upserted} players from 2025 rosters.")

    # Ingest 2025 Player Season Stats
    stats_inserted = 0
    stints_upserted = 0
    if not stats_2025.empty:
        # Refresh player map
        res = await session.execute(text("SELECT player_id, gsis_id FROM players WHERE gsis_id IS NOT NULL;"))
        player_id_by_gsis = {r[1]: r[0] for r in res.fetchall()}

        stat_records = []
        stint_records = []
        for _, srow in stats_2025.iterrows():
            gsis_id = clean_str(srow.get("player_id"))
            p_id = player_id_by_gsis.get(gsis_id)
            if not p_id:
                # If not found by gsis_id, try display name
                dname = clean_str(srow.get("player_display_name"))
                if dname and dname.lower() in player_id_by_name:
                    p_id = player_id_by_name[dname.lower()]
                else:
                    continue

            raw_team = clean_str(srow.get("recent_team") or srow.get("team"))
            if not raw_team:
                continue

            franchise_id = NFLDataTransformer.resolve_franchise_id(raw_team, 2025)
            team_season_id = f"{franchise_id}_2025"
            games_played = clean_int(srow.get("games")) or 1

            pass_yds = clean_int(srow.get("passing_yards")) or 0
            pass_tds = clean_int(srow.get("passing_tds")) or 0
            ints = clean_int(srow.get("passing_interceptions") or srow.get("interceptions")) or 0
            rush_yds = clean_int(srow.get("rushing_yards")) or 0
            rush_tds = clean_int(srow.get("rushing_tds")) or 0
            recs = clean_int(srow.get("receptions")) or 0
            rec_yds = clean_int(srow.get("receiving_yards")) or 0
            rec_tds = clean_int(srow.get("receiving_tds")) or 0
            sacks = clean_float(srow.get("def_sacks") or srow.get("sacks"))
            def_ints = clean_int(srow.get("def_interceptions") or srow.get("defensive_interceptions")) or 0

            stat_records.append({
                "player_id": p_id,
                "team_season_id": team_season_id,
                "passing_yards": pass_yds,
                "passing_tds": pass_tds,
                "interceptions": ints,
                "rushing_yards": rush_yds,
                "rushing_tds": rush_tds,
                "receptions": recs,
                "receiving_yards": rec_yds,
                "receiving_tds": rec_tds,
                "sacks": sacks,
                "defensive_interceptions": def_ints,
            })

            if games_played >= 1:
                stint_records.append({
                    "player_id": p_id,
                    "franchise_id": franchise_id,
                    "games_played": games_played,
                })

        stmt_stats = text("""
            INSERT INTO player_season_stats (
                player_id, team_season_id, season_year,
                passing_yards, passing_tds, interceptions,
                rushing_yards, rushing_tds, receptions,
                receiving_yards, receiving_tds, sacks, defensive_interceptions
            )
            VALUES (
                :player_id, :team_season_id, 2025,
                :passing_yards, :passing_tds, :interceptions,
                :rushing_yards, :rushing_tds, :receptions,
                :receiving_yards, :receiving_tds, :sacks, :defensive_interceptions
            )
            ON CONFLICT (player_id, team_season_id, season_year) DO UPDATE SET
                passing_yards = EXCLUDED.passing_yards,
                passing_tds = EXCLUDED.passing_tds,
                interceptions = EXCLUDED.interceptions,
                rushing_yards = EXCLUDED.rushing_yards,
                rushing_tds = EXCLUDED.rushing_tds,
                receptions = EXCLUDED.receptions,
                receiving_yards = EXCLUDED.receiving_yards,
                receiving_tds = EXCLUDED.receiving_tds,
                sacks = EXCLUDED.sacks,
                defensive_interceptions = EXCLUDED.defensive_interceptions;
        """)
        for i in range(0, len(stat_records), 500):
            await session.execute(stmt_stats, stat_records[i : i + 500])

        stmt_stints = text("""
            INSERT INTO player_team_stints (
                player_id, franchise_id, season_year, games_played, games_started
            )
            VALUES (
                :player_id, :franchise_id, 2025, :games_played, 0
            )
            ON CONFLICT (player_id, franchise_id, season_year) DO UPDATE SET
                games_played = GREATEST(player_team_stints.games_played, EXCLUDED.games_played);
        """)
        for i in range(0, len(stint_records), 500):
            await session.execute(stmt_stints, stint_records[i : i + 500])

        await session.commit()
        stats_inserted = len(stat_records)
        stints_upserted = len(stint_records)
        logger.info(f"Ingested {stats_inserted} 2025 player_season_stats records and {stints_upserted} stints.")

    return players_upserted, stats_inserted, stints_upserted


async def sync_2026_rosters(session: AsyncSession) -> Tuple[int, int]:
    """
    Ingests 2026 opening-week rosters and transactions, confirming active teams and jersey numbers.
    """
    logger.info("=== Starting 2026 Active Roster & Offseason Sync ===")
    
    rosters_2026 = fetch_rosters(2026)
    if rosters_2026.empty:
        rosters_2026 = fetch_weekly_rosters(2026)

    if rosters_2026.empty:
        logger.error("No 2026 roster data available!")
        return 0, 0

    # Load existing player maps
    res = await session.execute(text("SELECT player_id, gsis_id, pfr_id, full_name FROM players;"))
    rows = res.fetchall()
    player_id_by_gsis = {r[1]: r[0] for r in rows if r[1]}
    player_id_by_pfr = {r[2]: r[0] for r in rows if r[2]}
    player_id_by_name = {r[3].lower(): r[0] for r in rows if r[3]}

    name_col = "full_name" if "full_name" in rosters_2026.columns else "player_name"
    p2026_records = []
    stint2026_records = []
    seen_pids = set()

    for _, row in rosters_2026.iterrows():
        gsis_id = clean_str(row.get("gsis_id") or row.get("player_id"))
        pfr_id = clean_str(row.get("pfr_id"))
        full_name = clean_str(row.get(name_col))
        if not full_name:
            continue

        p_id = None
        if gsis_id and gsis_id in player_id_by_gsis:
            p_id = player_id_by_gsis[gsis_id]
        elif pfr_id and pfr_id in player_id_by_pfr:
            p_id = player_id_by_pfr[pfr_id]
        elif full_name.lower() in player_id_by_name:
            p_id = player_id_by_name[full_name.lower()]

        if not p_id:
            p_id = str(uuid.uuid4())
            if gsis_id:
                player_id_by_gsis[gsis_id] = p_id
            if pfr_id:
                player_id_by_pfr[pfr_id] = p_id

        if pfr_id and pfr_id in player_id_by_pfr and player_id_by_pfr[pfr_id] != p_id:
            pfr_id = None
        if gsis_id and gsis_id in player_id_by_gsis and player_id_by_gsis[gsis_id] != p_id:
            gsis_id = None

        if p_id not in seen_pids:
            seen_pids.add(p_id)
            name_parts = full_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            pos = clean_str(row.get("position")) or "ATH"
            college = clean_str(row.get("college"))
            headshot = clean_str(row.get("headshot_url"))
            jersey = clean_int(row.get("jersey_number"))
            draft_yr = clean_int(row.get("entry_year") or row.get("rookie_year") or row.get("draft_year"))
            draft_rd = clean_int(row.get("draft_round"))
            draft_num = clean_int(row.get("draft_number"))
            rookie_yr = clean_int(row.get("rookie_year") or row.get("entry_year")) or 2026

            p2026_records.append({
                "player_id": p_id,
                "gsis_id": gsis_id,
                "pfr_id": pfr_id,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_position": pos[:10],
                "draft_year": draft_yr,
                "draft_round": draft_rd,
                "draft_overall": draft_num,
                "college": college[:100] if college else None,
                "rookie_year": rookie_yr,
                "headshot_url": headshot[:255] if headshot else None,
                "jersey_number": jersey,
            })

        raw_team = clean_str(row.get("team"))
        if raw_team:
            franchise_id = NFLDataTransformer.resolve_franchise_id(raw_team, 2026)
            stint2026_records.append({
                "player_id": p_id,
                "franchise_id": franchise_id,
            })

    stmt_p2026 = text("""
        INSERT INTO players (
            player_id, gsis_id, pfr_id, full_name, first_name, last_name,
            primary_position, draft_year, draft_round, draft_overall,
            college, rookie_year, final_year, is_active, headshot_url, jersey_number
        )
        VALUES (
            :player_id, :gsis_id, :pfr_id, :full_name, :first_name, :last_name,
            :primary_position, :draft_year, :draft_round, :draft_overall,
            :college, :rookie_year, NULL, true, :headshot_url, :jersey_number
        )
        ON CONFLICT (player_id) DO UPDATE SET
            gsis_id = COALESCE(players.gsis_id, EXCLUDED.gsis_id),
            pfr_id = COALESCE(players.pfr_id, EXCLUDED.pfr_id),
            full_name = EXCLUDED.full_name,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            primary_position = EXCLUDED.primary_position,
            college = COALESCE(players.college, EXCLUDED.college),
            draft_year = COALESCE(players.draft_year, EXCLUDED.draft_year),
            draft_round = COALESCE(players.draft_round, EXCLUDED.draft_round),
            draft_overall = COALESCE(players.draft_overall, EXCLUDED.draft_overall),
            is_active = true,
            final_year = NULL,
            headshot_url = COALESCE(EXCLUDED.headshot_url, players.headshot_url),
            jersey_number = COALESCE(EXCLUDED.jersey_number, players.jersey_number);
    """)
    for i in range(0, len(p2026_records), 500):
        await session.execute(stmt_p2026, p2026_records[i : i + 500])

    stmt_stint2026 = text("""
        INSERT INTO player_team_stints (
            player_id, franchise_id, season_year, games_played, games_started
        )
        VALUES (
            :player_id, :franchise_id, 2026, 1, 0
        )
        ON CONFLICT (player_id, franchise_id, season_year) DO UPDATE SET
            games_played = GREATEST(player_team_stints.games_played, 1);
    """)
    for i in range(0, len(stint2026_records), 500):
        await session.execute(stmt_stint2026, stint2026_records[i : i + 500])

    await session.commit()
    players_synced = len(p2026_records)
    stints_synced = len(stint2026_records)
    logger.info(f"Synced {players_synced} active players and {stints_synced} 2026 team stints.")
    return players_synced, stints_synced


async def recompute_career_stats(session: AsyncSession) -> int:
    """
    Precomputes and bulk updates player_career_stats from season stats, stints, and accolades.
    """
    logger.info("Recomputing player career statistics...")
    
    # Bulk aggregate SQL query
    stmt = text("""
        INSERT INTO player_career_stats (
            player_id, seasons_played, games_played,
            passing_yards, passing_tds, interceptions,
            rushing_yards, rushing_tds, receptions,
            receiving_yards, receiving_tds, sacks,
            defensive_interceptions, pro_bowls, all_pros,
            franchises_played_count
        )
        SELECT 
            p.player_id,
            COALESCE(stat_agg.seasons, 0) AS seasons_played,
            COALESCE(stint_agg.total_gp, 0) AS games_played,
            COALESCE(stat_agg.pass_yds, 0) AS passing_yards,
            COALESCE(stat_agg.pass_tds, 0) AS passing_tds,
            COALESCE(stat_agg.ints, 0) AS interceptions,
            COALESCE(stat_agg.rush_yds, 0) AS rushing_yards,
            COALESCE(stat_agg.rush_tds, 0) AS rushing_tds,
            COALESCE(stat_agg.recs, 0) AS receptions,
            COALESCE(stat_agg.rec_yds, 0) AS receiving_yards,
            COALESCE(stat_agg.rec_tds, 0) AS receiving_tds,
            COALESCE(stat_agg.sacks, 0.0) AS sacks,
            COALESCE(stat_agg.def_ints, 0) AS defensive_interceptions,
            COALESCE(acc_pb.pb_cnt, 0) AS pro_bowls,
            COALESCE(acc_ap.ap_cnt, 0) AS all_pros,
            COALESCE(stint_agg.franchise_cnt, 0) AS franchises_played_count
        FROM players p
        LEFT JOIN (
            SELECT 
                player_id,
                COUNT(stat_id) AS seasons,
                SUM(passing_yards) AS pass_yds,
                SUM(passing_tds) AS pass_tds,
                SUM(interceptions) AS ints,
                SUM(rushing_yards) AS rush_yds,
                SUM(rushing_tds) AS rush_tds,
                SUM(receptions) AS recs,
                SUM(receiving_yards) AS rec_yds,
                SUM(receiving_tds) AS rec_tds,
                SUM(sacks) AS sacks,
                SUM(defensive_interceptions) AS def_ints
            FROM player_season_stats
            GROUP BY player_id
        ) stat_agg ON p.player_id = stat_agg.player_id
        LEFT JOIN (
            SELECT 
                player_id,
                SUM(games_played) AS total_gp,
                COUNT(DISTINCT franchise_id) AS franchise_cnt
            FROM player_team_stints
            WHERE games_played >= 1
            GROUP BY player_id
        ) stint_agg ON p.player_id = stint_agg.player_id
        LEFT JOIN (
            SELECT player_id, COUNT(*) AS pb_cnt
            FROM accolades
            WHERE accolade_type = 'PRO_BOWL'
            GROUP BY player_id
        ) acc_pb ON p.player_id = acc_pb.player_id
        LEFT JOIN (
            SELECT player_id, COUNT(*) AS ap_cnt
            FROM accolades
            WHERE accolade_type = 'FIRST_TEAM_ALL_PRO'
            GROUP BY player_id
        ) acc_ap ON p.player_id = acc_ap.player_id
        WHERE stat_agg.player_id IS NOT NULL OR stint_agg.player_id IS NOT NULL
        ON CONFLICT (player_id) DO UPDATE SET
            seasons_played = EXCLUDED.seasons_played,
            games_played = EXCLUDED.games_played,
            passing_yards = EXCLUDED.passing_yards,
            passing_tds = EXCLUDED.passing_tds,
            interceptions = EXCLUDED.interceptions,
            rushing_yards = EXCLUDED.rushing_yards,
            rushing_tds = EXCLUDED.rushing_tds,
            receptions = EXCLUDED.receptions,
            receiving_yards = EXCLUDED.receiving_yards,
            receiving_tds = EXCLUDED.receiving_tds,
            sacks = EXCLUDED.sacks,
            defensive_interceptions = EXCLUDED.defensive_interceptions,
            pro_bowls = EXCLUDED.pro_bowls,
            all_pros = EXCLUDED.all_pros,
            franchises_played_count = EXCLUDED.franchises_played_count;
    """)
    res = await session.execute(stmt)
    await session.commit()
    logger.info("Player career statistics successfully precomputed.")
    return res.rowcount if hasattr(res, "rowcount") else 0


async def run_pipeline() -> None:
    logger.info("Initializing Database Connection...")
    engine = create_async_engine(
        settings.async_database_url,
        echo=False,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Step 1: Seed Team Seasons for 2025 and 2026
        await seed_team_seasons(session, [2025, 2026])

        # Step 2: Ingest 2025 Season stats and stints
        await sync_2025_season(session)

        # Step 3: Ingest 2026 Opening-Week Rosters and active stints
        await sync_2026_rosters(session)

        # Step 4: Recompute Career Stats
        await recompute_career_stats(session)

    await engine.dispose()
    logger.info("2025/2026 Sync Pipeline successfully completed.")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
