#!/usr/bin/env python3
"""
backfill_players_canonical.py
-----------------------------
Backfills PostgreSQL `players` table with canonical biographical and career span metadata:
- Canonical `rookie_year` from nflverse `rookie_season` / `draft_year` / stint minimums.
- Canonical `final_year` and `is_active` status for retired players vs active players.
- Draft metadata (draft_year, draft_round, draft_overall) and college.
- Refreshes client search index.
"""

import asyncio
import datetime
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "..", "..", "apps", "api")
ETL_DIR = os.path.join(CURRENT_DIR, "..")

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if ETL_DIR not in sys.path:
    sys.path.insert(0, ETL_DIR)

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backfill_players_canonical")

# Known retired legends / modern retirees override map to guarantee 100% accuracy
RETIRED_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "Tom Brady": {"rookie_year": 2000, "final_year": 2022, "is_active": False},
    "Peyton Manning": {"rookie_year": 1998, "final_year": 2015, "is_active": False},
    "Dan Marino": {"rookie_year": 1983, "final_year": 1999, "is_active": False},
    "Brett Favre": {"rookie_year": 1991, "final_year": 2010, "is_active": False},
    "Aaron Donald": {"rookie_year": 2014, "final_year": 2023, "is_active": False},
    "Drew Brees": {"rookie_year": 2001, "final_year": 2020, "is_active": False},
    "Eli Manning": {"rookie_year": 2004, "final_year": 2019, "is_active": False},
    "Ben Roethlisberger": {"rookie_year": 2004, "final_year": 2021, "is_active": False},
    "Philip Rivers": {"rookie_year": 2004, "final_year": 2020, "is_active": False},
    "Matt Ryan": {"rookie_year": 2008, "final_year": 2022, "is_active": False},
    "Frank Gore": {"rookie_year": 2005, "final_year": 2020, "is_active": False},
    "Adrian Peterson": {"rookie_year": 2007, "final_year": 2021, "is_active": False},
    "Jason Kelce": {"rookie_year": 2011, "final_year": 2023, "is_active": False},
    "J.J. Watt": {"rookie_year": 2011, "final_year": 2022, "is_active": False},
    "Rob Gronkowski": {"rookie_year": 2010, "final_year": 2021, "is_active": False},
    "Larry Fitzgerald": {"rookie_year": 2004, "final_year": 2020, "is_active": False},
    "Andrew Luck": {"rookie_year": 2012, "final_year": 2018, "is_active": False},
    "Joe Montana": {"rookie_year": 1979, "final_year": 1994, "is_active": False},
    "John Elway": {"rookie_year": 1983, "final_year": 1998, "is_active": False},
    "Steve Young": {"rookie_year": 1985, "final_year": 1999, "is_active": False},
    "Troy Aikman": {"rookie_year": 1989, "final_year": 2000, "is_active": False},
    "Warren Moon": {"rookie_year": 1984, "final_year": 2000, "is_active": False},
    "Terry Bradshaw": {"rookie_year": 1970, "final_year": 1983, "is_active": False},
    "Emmitt Smith": {"rookie_year": 1990, "final_year": 2004, "is_active": False},
    "Barry Sanders": {"rookie_year": 1989, "final_year": 1998, "is_active": False},
    "Walter Payton": {"rookie_year": 1975, "final_year": 1987, "is_active": False},
    "Jerry Rice": {"rookie_year": 1985, "final_year": 2004, "is_active": False},
    "Randy Moss": {"rookie_year": 1998, "final_year": 2012, "is_active": False},
    "Terrell Owens": {"rookie_year": 1996, "final_year": 2010, "is_active": False},
    "Calvin Johnson": {"rookie_year": 2007, "final_year": 2015, "is_active": False},
    "Tony Gonzalez": {"rookie_year": 1997, "final_year": 2013, "is_active": False},
    "Shannon Sharpe": {"rookie_year": 1990, "final_year": 2003, "is_active": False},
    "Reggie White": {"rookie_year": 1985, "final_year": 2000, "is_active": False},
    "Bruce Smith": {"rookie_year": 1985, "final_year": 2003, "is_active": False},
    "Michael Strahan": {"rookie_year": 1993, "final_year": 2007, "is_active": False},
    "Lawrence Taylor": {"rookie_year": 1981, "final_year": 1993, "is_active": False},
    "Ray Lewis": {"rookie_year": 1996, "final_year": 2012, "is_active": False},
    "Brian Urlacher": {"rookie_year": 2000, "final_year": 2012, "is_active": False},
    "Deion Sanders": {"rookie_year": 1989, "final_year": 2005, "is_active": False},
    "Charles Woodson": {"rookie_year": 1998, "final_year": 2015, "is_active": False},
    "Ed Reed": {"rookie_year": 2002, "final_year": 2013, "is_active": False},
    "Troy Polamalu": {"rookie_year": 2003, "final_year": 2014, "is_active": False},
    "Richard Sherman": {"rookie_year": 2011, "final_year": 2021, "is_active": False},
    "Luke Kuechly": {"rookie_year": 2012, "final_year": 2019, "is_active": False},
    "DeMarcus Ware": {"rookie_year": 2005, "final_year": 2016, "is_active": False},
    "Julius Peppers": {"rookie_year": 2002, "final_year": 2018, "is_active": False},
    "Darrelle Revis": {"rookie_year": 2007, "final_year": 2017, "is_active": False},
    "Champ Bailey": {"rookie_year": 1999, "final_year": 2013, "is_active": False},
}


def load_nflverse_players() -> pd.DataFrame:
    """Loads universal players catalog from nflverse."""
    try:
        import nflreadpy as nfl
        logger.info("Loading nflverse players via nflreadpy...")
        df = nfl.load_players()
        return df.to_pandas() if hasattr(df, "to_pandas") else df
    except Exception as exc:
        logger.warning(f"nflreadpy unavailable ({exc}); loading from nflverse GitHub release.")
        url = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
        return pd.read_csv(url, low_memory=False)


async def backfill_players(db_url: Optional[str] = None):
    url = db_url or settings.async_database_url
    logger.info(f"Connecting to database: {url}")
    engine = create_async_engine(url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    df_players = load_nflverse_players()
    logger.info(f"Loaded {len(df_players)} records from nflverse players table.")

    # Index nflverse by gsis_id, pfr_id, and normalized name
    by_gsis: Dict[str, Any] = {}
    by_pfr: Dict[str, Any] = {}
    by_name: Dict[str, Any] = {}

    for _, row in df_players.iterrows():
        g_id = str(row.get("gsis_id", "")).strip()
        if g_id and g_id != "nan":
            by_gsis[g_id] = row

        p_id = str(row.get("pfr_id", "")).strip()
        if p_id and p_id != "nan":
            by_pfr[p_id] = row

        d_name = str(row.get("display_name", "")).strip().lower()
        if d_name and d_name != "nan" and d_name not in by_name:
            by_name[d_name] = row

    current_year = datetime.datetime.now().year

    async with session_maker() as session:
        # Fetch all players in DB with their stint stats
        logger.info("Querying all players and stint boundaries from database...")
        query = text("""
            SELECT 
                p.player_id, p.gsis_id, p.pfr_id, p.full_name, p.primary_position,
                p.rookie_year, p.final_year, p.is_active,
                p.draft_year, p.draft_round, p.draft_overall, p.college, p.headshot_url,
                MIN(s.season_year) as min_stint,
                MAX(s.season_year) as max_stint
            FROM players p
            LEFT JOIN player_team_stints s ON p.player_id = s.player_id
            GROUP BY p.player_id;
        """)
        rows = (await session.execute(query)).fetchall()
        logger.info(f"Found {len(rows)} players in database to audit.")

        updates = []
        updated_rookie_count = 0
        updated_retired_count = 0

        for r in rows:
            (
                p_id, gsis_id, pfr_id, full_name, pos,
                cur_rookie, cur_final, cur_active,
                draft_yr, draft_rnd, draft_ovr, college, headshot,
                min_stint, max_stint
            ) = r

            norm_name = full_name.strip().lower()

            # Find matching nflverse row
            nv_row = None
            if gsis_id and gsis_id in by_gsis:
                nv_row = by_gsis[gsis_id]
            elif pfr_id and pfr_id in by_pfr:
                nv_row = by_pfr[pfr_id]
            elif norm_name in by_name:
                nv_row = by_name[norm_name]

            # 1. Resolve canonical rookie year
            canonical_rookie = None
            if nv_row is not None:
                raw_rs = nv_row.get("rookie_season")
                if pd.notna(raw_rs):
                    try:
                        canonical_rookie = int(raw_rs)
                    except (ValueError, TypeError):
                        pass
                if canonical_rookie is None or canonical_rookie < 1920:
                    raw_dy = nv_row.get("draft_year")
                    if pd.notna(raw_dy):
                        try:
                            canonical_rookie = int(raw_dy)
                        except (ValueError, TypeError):
                            pass

            if canonical_rookie is None and draft_yr:
                canonical_rookie = int(draft_yr)

            # Check explicit overrides
            override = RETIRED_OVERRIDES.get(full_name)
            if override:
                new_rookie = override["rookie_year"]
                new_final = override["final_year"]
                new_active = override["is_active"]
            else:
                candidates = []
                if canonical_rookie and 1920 <= canonical_rookie <= current_year + 1:
                    candidates.append(canonical_rookie)
                if min_stint and 1920 <= min_stint <= current_year + 1:
                    candidates.append(min_stint)
                if cur_rookie and cur_rookie != 2020 and 1920 <= cur_rookie <= current_year + 1:
                    candidates.append(cur_rookie)
                elif cur_rookie and not candidates:
                    candidates.append(cur_rookie)

                new_rookie = min(candidates) if candidates else (cur_rookie or 2020)

                # 2. Resolve active vs retired & final_year
                nv_last = None
                nv_status = ""
                if nv_row is not None:
                    raw_ls = nv_row.get("last_season")
                    if pd.notna(raw_ls):
                        try:
                            nv_last = int(raw_ls)
                        except (ValueError, TypeError):
                            pass
                    raw_st = nv_row.get("status")
                    if pd.notna(raw_st):
                        nv_status = str(raw_st).strip().upper()

                # Determine is_active
                if nv_status in ("RET", "EXE", "HON"):
                    new_active = False
                elif max_stint and max_stint >= current_year:
                    new_active = True
                elif nv_status == "ACT" and ((max_stint and max_stint >= current_year - 1) or (nv_last and nv_last >= current_year)):
                    new_active = True
                elif cur_active and ((max_stint and max_stint >= current_year) or new_rookie >= 2023):
                    new_active = True
                else:
                    new_active = False

                if new_active:
                    new_final = None
                else:
                    final_candidates = []
                    if cur_final:
                        final_candidates.append(cur_final)
                    if nv_last:
                        final_candidates.append(nv_last)
                    if max_stint:
                        final_candidates.append(max_stint)

                    if final_candidates:
                        new_final = max(final_candidates)
                    else:
                        new_final = min(new_rookie + 12, current_year - 1)

            # Metadata enrichment
            new_draft_yr = draft_yr
            new_draft_rnd = draft_rnd
            new_draft_ovr = draft_ovr
            new_college = college
            new_pfr = pfr_id
            new_gsis = gsis_id
            new_headshot = headshot

            if nv_row is not None:
                if not new_pfr and pd.notna(nv_row.get("pfr_id")):
                    new_pfr = str(nv_row["pfr_id"])[:40]
                if not new_gsis and pd.notna(nv_row.get("gsis_id")):
                    new_gsis = str(nv_row["gsis_id"])[:50]
                if not new_college and pd.notna(nv_row.get("college_name")):
                    new_college = str(nv_row["college_name"])[:100]
                if not new_headshot and pd.notna(nv_row.get("headshot")):
                    new_headshot = str(nv_row["headshot"])[:255]
                if new_draft_yr is None and pd.notna(nv_row.get("draft_year")):
                    try:
                        new_draft_yr = int(nv_row["draft_year"])
                    except (ValueError, TypeError):
                        pass
                if new_draft_rnd is None and pd.notna(nv_row.get("draft_round")):
                    try:
                        new_draft_rnd = int(nv_row["draft_round"])
                    except (ValueError, TypeError):
                        pass
                if new_draft_ovr is None and pd.notna(nv_row.get("draft_pick")):
                    try:
                        new_draft_ovr = int(nv_row["draft_pick"])
                    except (ValueError, TypeError):
                        pass

            if new_rookie != cur_rookie:
                updated_rookie_count += 1
            if new_final != cur_final or new_active != cur_active:
                updated_retired_count += 1

            updates.append({
                "p_id": p_id,
                "rookie_year": new_rookie,
                "final_year": new_final,
                "is_active": new_active,
                "draft_year": new_draft_yr,
                "draft_round": new_draft_rnd,
                "draft_overall": new_draft_ovr,
                "college": new_college,
                "pfr_id": new_pfr,
                "gsis_id": new_gsis,
                "headshot_url": new_headshot,
            })

        logger.info(f"Applying canonical updates to {len(updates)} players...")
        logger.info(f" - Rookie years updated: {updated_rookie_count}")
        logger.info(f" - Retirement/active statuses updated: {updated_retired_count}")

        update_stmt = text("""
            UPDATE players SET
                rookie_year = :rookie_year,
                final_year = :final_year,
                is_active = :is_active,
                draft_year = :draft_year,
                draft_round = :draft_round,
                draft_overall = :draft_overall,
                college = :college,
                headshot_url = COALESCE(players.headshot_url, :headshot_url)
            WHERE player_id = :p_id;
        """)

        chunk_size = 500
        for i in range(0, len(updates), chunk_size):
            chunk = updates[i : i + chunk_size]
            await session.execute(update_stmt, chunk)
        await session.commit()
        logger.info("Database backfill completed successfully!")

        # Refresh client search index
        logger.info("Regenerating client search index...")
        search_query = text("""
            SELECT 
                p.player_id, 
                p.full_name, 
                p.primary_position, 
                p.rookie_year, 
                CASE 
                    WHEN p.is_active = FALSE AND p.final_year IS NULL THEN (
                        SELECT MAX(s.season_year) 
                        FROM player_team_stints s 
                        WHERE s.player_id = p.player_id
                    )
                    ELSE p.final_year 
                END AS final_year, 
                p.is_active
            FROM players p
            ORDER BY p.is_active DESC, final_year DESC NULLS FIRST, p.full_name ASC;
        """)
        s_rows = (await session.execute(search_query)).fetchall()

        player_records = [
            [
                r[0],  # id
                r[1],  # name
                r[2],  # pos
                r[3],  # start
                r[4],  # end
                1 if r[5] else 0,  # active
            ]
            for r in s_rows
        ]

        payload = {
            "version": datetime.datetime.now(datetime.timezone.utc).strftime("%Y.%m.%d.canonical"),
            "fields": ["id", "name", "pos", "start", "end", "active"],
            "players": player_records,
        }

        out_path = os.path.join(CURRENT_DIR, "..", "..", "..", "apps", "web", "public", "player_search_index.json")
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))

        logger.info(f"Updated client search index at {out_path} with {len(player_records)} players.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill_players())
