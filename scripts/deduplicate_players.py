#!/usr/bin/env python3
"""
deduplicate_players.py
----------------------
Identifies duplicate player entities in PostgreSQL:
1. Merges metadata (gsis_id, pfr_id, draft info, rookie/final year, active status, college, headshot).
2. Re-points all foreign keys in:
   - player_team_stints
   - player_season_stats
   - accolades
   - aggregated_answer_stats
   - player_career_stats
3. Eliminates duplicate stints / accolades on conflict.
4. Purges orphan duplicate player records.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "apps", "api")
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("deduplicate_players")


async def deduplicate_players():
    engine = create_async_engine(settings.async_database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        logger.info("Scanning for duplicate player entities...")

        # 1. Detect duplicates by identical GSIS ID
        q_gsis = text("""
            SELECT gsis_id, ARRAY_AGG(player_id ORDER BY (draft_round IS NOT NULL) DESC, rookie_year ASC)
            FROM players
            WHERE gsis_id IS NOT NULL AND gsis_id != ''
            GROUP BY gsis_id
            HAVING COUNT(*) > 1;
        """)
        gsis_dups = (await session.execute(q_gsis)).fetchall()
        logger.info(f"Found {len(gsis_dups)} duplicate GSIS ID groups.")

        # 2. Detect duplicates by identical PFR ID
        q_pfr = text("""
            SELECT pfr_id, ARRAY_AGG(player_id ORDER BY (draft_round IS NOT NULL) DESC, rookie_year ASC)
            FROM players
            WHERE pfr_id IS NOT NULL AND pfr_id != ''
            GROUP BY pfr_id
            HAVING COUNT(*) > 1;
        """)
        pfr_dups = (await session.execute(q_pfr)).fetchall()
        logger.info(f"Found {len(pfr_dups)} duplicate PFR ID groups.")

        # 3. Detect duplicates by exact full_name where one record lacks gsis_id (e.g. from HOF seed)
        q_name = text("""
            SELECT LOWER(full_name), ARRAY_AGG(player_id ORDER BY (gsis_id IS NOT NULL) DESC, (draft_round IS NOT NULL) DESC)
            FROM players
            GROUP BY LOWER(full_name)
            HAVING COUNT(*) > 1;
        """)
        name_dups = (await session.execute(q_name)).fetchall()
        logger.info(f"Found {len(name_dups)} duplicate full_name groups.")

        # Aggregate merge mapping: duplicate_id -> canonical_id
        merge_map: Dict[str, str] = {}

        for _, id_list in gsis_dups:
            canonical_id = id_list[0]
            for dup_id in id_list[1:]:
                merge_map[dup_id] = canonical_id

        for _, id_list in pfr_dups:
            canonical_id = id_list[0]
            for dup_id in id_list[1:]:
                if dup_id not in merge_map:
                    merge_map[dup_id] = canonical_id

        # For name duplicates: only merge if positions match or one has NULL gsis_id
        for _, id_list in name_dups:
            # Query full details for players in this group
            p_stmt = text("""
                SELECT player_id, gsis_id, pfr_id, primary_position, rookie_year, draft_year
                FROM players
                WHERE player_id = ANY(:ids);
            """)
            p_rows = (await session.execute(p_stmt, {"ids": id_list})).fetchall()
            if len(p_rows) <= 1:
                continue

            # Check if there is one row with GSIS and one without GSIS (e.g. HOF seed vs nflverse)
            with_gsis = [r for r in p_rows if r[1] is not None and str(r[1]).startswith("00-")]
            without_gsis = [r for r in p_rows if r[1] is None or not str(r[1]).startswith("00-")]

            if with_gsis and without_gsis:
                canon = with_gsis[0][0]
                for r in without_gsis:
                    dup = r[0]
                    # Check if rookie years are close (within 5 years) to avoid merging father/son players
                    if abs((r[4] or 2000) - (with_gsis[0][4] or 2000)) <= 5:
                        merge_map[dup] = canon

        logger.info(f"Total player records identified for merging: {len(merge_map)}")

        merged_count = 0
        for dup_id, canon_id in merge_map.items():
            if dup_id == canon_id:
                continue

            # Fetch both player records
            p_get = text("SELECT * FROM players WHERE player_id IN (:canon, :dup)")
            rows = (await session.execute(p_get, {"canon": canon_id, "dup": dup_id})).mappings().all()
            if len(rows) < 2:
                continue

            canon_row = next((r for r in rows if r["player_id"] == canon_id), None)
            dup_row = next((r for r in rows if r["player_id"] == dup_id), None)

            if not canon_row or not dup_row:
                continue

            # Merge metadata onto canonical player
            update_player = text("""
                UPDATE players SET
                    gsis_id = COALESCE(players.gsis_id, CAST(:gsis_id AS VARCHAR)),
                    pfr_id = COALESCE(players.pfr_id, CAST(:pfr_id AS VARCHAR)),
                    draft_year = COALESCE(players.draft_year, CAST(:draft_year AS SMALLINT)),
                    draft_round = COALESCE(players.draft_round, CAST(:draft_round AS SMALLINT)),
                    draft_overall = COALESCE(players.draft_overall, CAST(:draft_overall AS SMALLINT)),
                    college = COALESCE(players.college, CAST(:college AS VARCHAR)),
                    rookie_year = LEAST(players.rookie_year, CAST(:rookie_year AS SMALLINT)),
                    final_year = CASE 
                        WHEN players.final_year IS NULL OR CAST(:final_year AS SMALLINT) IS NULL THEN NULL 
                        ELSE GREATEST(players.final_year, CAST(:final_year AS SMALLINT)) 
                    END,
                    is_active = (players.is_active OR CAST(:is_active AS BOOLEAN)),
                    headshot_url = COALESCE(players.headshot_url, CAST(:headshot_url AS VARCHAR))
                WHERE player_id = :canon_id;
            """)
            await session.execute(update_player, {
                "canon_id": canon_id,
                "gsis_id": dup_row["gsis_id"],
                "pfr_id": dup_row["pfr_id"],
                "draft_year": dup_row["draft_year"],
                "draft_round": dup_row["draft_round"],
                "draft_overall": dup_row["draft_overall"],
                "college": dup_row["college"],
                "rookie_year": dup_row["rookie_year"] or canon_row["rookie_year"],
                "final_year": dup_row["final_year"],
                "is_active": dup_row["is_active"],
                "headshot_url": dup_row["headshot_url"],
            })

            # Reassign player_team_stints
            stints_dup = text("SELECT stint_id, franchise_id, season_year, games_played, games_started FROM player_team_stints WHERE player_id = :dup")
            d_stints = (await session.execute(stints_dup, {"dup": dup_id})).fetchall()
            for s in d_stints:
                # Upsert into canon_id
                upsert_s = text("""
                    INSERT INTO player_team_stints (player_id, franchise_id, season_year, games_played, games_started)
                    VALUES (:canon_id, :fid, :yr, :gp, :gs)
                    ON CONFLICT (player_id, franchise_id, season_year) DO UPDATE SET
                        games_played = GREATEST(player_team_stints.games_played, EXCLUDED.games_played),
                        games_started = GREATEST(player_team_stints.games_started, EXCLUDED.games_started);
                """)
                await session.execute(upsert_s, {
                    "canon_id": canon_id,
                    "fid": s[1],
                    "yr": s[2],
                    "gp": s[3],
                    "gs": s[4],
                })
            # Delete duplicate stints
            await session.execute(text("DELETE FROM player_team_stints WHERE player_id = :dup"), {"dup": dup_id})

            # Reassign accolades
            acc_dup = text("SELECT accolade_id, franchise_id, season_year, accolade_type, category FROM accolades WHERE player_id = :dup")
            d_acc = (await session.execute(acc_dup, {"dup": dup_id})).fetchall()
            for a in d_acc:
                upsert_a = text("""
                    INSERT INTO accolades (player_id, franchise_id, season_year, accolade_type, category)
                    VALUES (:canon_id, :fid, :yr, :atype, :cat)
                    ON CONFLICT DO NOTHING;
                """)
                await session.execute(upsert_a, {
                    "canon_id": canon_id,
                    "fid": a[1],
                    "yr": a[2],
                    "atype": a[3],
                    "cat": a[4],
                })
            await session.execute(text("DELETE FROM accolades WHERE player_id = :dup"), {"dup": dup_id})

            # Reassign player_season_stats
            stats_dup = text("SELECT stat_id, team_season_id, season_year, passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds, receptions, receiving_yards, receiving_tds, sacks, defensive_interceptions FROM player_season_stats WHERE player_id = :dup")
            d_stats = (await session.execute(stats_dup, {"dup": dup_id})).fetchall()
            for st in d_stats:
                upsert_st = text("""
                    INSERT INTO player_season_stats (
                        player_id, team_season_id, season_year, passing_yards, passing_tds, interceptions,
                        rushing_yards, rushing_tds, receptions, receiving_yards, receiving_tds, sacks, defensive_interceptions
                    )
                    VALUES (:canon_id, :tsid, :yr, :pyd, :ptd, :int, :ryd, :rtd, :rec, :recy, :rectd, :sacks, :dint)
                    ON CONFLICT (player_id, team_season_id, season_year) DO NOTHING;
                """)
                await session.execute(upsert_st, {
                    "canon_id": canon_id,
                    "tsid": st[1],
                    "yr": st[2],
                    "pyd": st[3],
                    "ptd": st[4],
                    "int": st[5],
                    "ryd": st[6],
                    "rtd": st[7],
                    "rec": st[8],
                    "recy": st[9],
                    "rectd": st[10],
                    "sacks": st[11],
                    "dint": st[12],
                })
            await session.execute(text("DELETE FROM player_season_stats WHERE player_id = :dup"), {"dup": dup_id})

            # Reassign aggregated_answer_stats
            ans_dup = text("SELECT stat_id, puzzle_id, cell_identifier, selection_count, pick_percentage FROM aggregated_answer_stats WHERE player_id = :dup")
            d_ans = (await session.execute(ans_dup, {"dup": dup_id})).fetchall()
            for ans in d_ans:
                upsert_ans = text("""
                    INSERT INTO aggregated_answer_stats (puzzle_id, cell_identifier, player_id, selection_count, pick_percentage)
                    VALUES (:puz, :cell, :canon_id, :cnt, :pct)
                    ON CONFLICT (puzzle_id, cell_identifier, player_id) DO UPDATE SET
                        selection_count = aggregated_answer_stats.selection_count + EXCLUDED.selection_count;
                """)
                await session.execute(upsert_ans, {
                    "puz": ans[1],
                    "cell": ans[2],
                    "canon_id": canon_id,
                    "cnt": ans[3],
                    "pct": ans[4],
                })
            await session.execute(text("DELETE FROM aggregated_answer_stats WHERE player_id = :dup"), {"dup": dup_id})

            # Delete player_career_stats for duplicate
            await session.execute(text("DELETE FROM player_career_stats WHERE player_id = :dup"), {"dup": dup_id})

            # Finally delete the duplicate player row
            await session.execute(text("DELETE FROM players WHERE player_id = :dup"), {"dup": dup_id})
            merged_count += 1

        await session.commit()
        logger.info(f"Deduplication complete! Successfully unified {merged_count} duplicate player entities.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(deduplicate_players())
