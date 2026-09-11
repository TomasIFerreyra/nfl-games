import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def main():
    engine = create_async_engine(settings.async_database_url)
    async with engine.connect() as conn:
        print("=" * 80)
        print("FORENSIC DIAGNOSTIC RESULTS")
        print("=" * 80)

        print("\n--- 1. DUPLICATE / MULTIPLE ROWS IN PLAYERS TABLE ---")
        q1 = text("""
            SELECT player_id, gsis_id, pfr_id, full_name, draft_year, draft_round, draft_overall, rookie_year, final_year, is_active
            FROM players 
            WHERE full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
            ORDER BY full_name, player_id;
        """)
        rows1 = (await conn.execute(q1)).fetchall()
        for r in rows1:
            print(" ", r)

        print("\n--- 2. STINTS REGISTERED FOR TARGET PLAYERS ---")
        q2 = text("""
            SELECT p.player_id, p.full_name, pts.franchise_id, pts.season_year, pts.games_played
            FROM player_team_stints pts
            JOIN players p ON p.player_id = pts.player_id
            WHERE p.full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
            ORDER BY p.full_name, pts.season_year, pts.franchise_id;
        """)
        rows2 = (await conn.execute(q2)).fetchall()
        print(f"Total stints found for target players: {len(rows2)}")
        for r in rows2:
            print(" ", r)

        print("\n--- 3. ACCOLADES REGISTERED FOR TARGET PLAYERS ---")
        q3 = text("""
            SELECT p.player_id, p.full_name, a.accolade_id, a.accolade_type, a.season_year, a.franchise_id
            FROM accolades a
            JOIN players p ON p.player_id = a.player_id
            WHERE p.full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
            ORDER BY p.full_name, a.season_year, a.accolade_type;
        """)
        rows3 = (await conn.execute(q3)).fetchall()
        print(f"Total accolades found for target players: {len(rows3)}")
        for r in rows3:
            print(" ", r)

        print("\n--- 4. DUPLICATE PLAYER NAMES IN ENTIRE DATABASE ---")
        q4 = text("""
            SELECT full_name, COUNT(*) AS count_duplicates, ARRAY_AGG(player_id) AS player_ids, ARRAY_AGG(gsis_id) AS gsis_ids
            FROM players
            GROUP BY full_name
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
            LIMIT 30;
        """)
        rows4 = (await conn.execute(q4)).fetchall()
        print(f"Duplicate player name groups found (showing up to 30): {len(rows4)}")
        for r in rows4:
            print(f"  {r[0]:<25} Duplicates: {r[1]} | IDs: {r[2]} | GSIS: {r[3]}")

        print("\n--- 5. DISTINCT ACCOLADE TYPES IN DATABASE ---")
        q5 = text("SELECT DISTINCT accolade_type, count(*) FROM accolades GROUP BY accolade_type;")
        rows5 = (await conn.execute(q5)).fetchall()
        for r in rows5:
            print(" ", r)

        print("\n--- 6. DRAFT ROUND VALUES IN PLAYERS TABLE ---")
        q6 = text("""
            SELECT draft_round, count(*)
            FROM players
            WHERE draft_year >= 2020
            GROUP BY draft_round
            ORDER BY draft_round NULLS LAST;
        """)
        rows6 = (await conn.execute(q6)).fetchall()
        for r in rows6:
            print(" ", r)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
