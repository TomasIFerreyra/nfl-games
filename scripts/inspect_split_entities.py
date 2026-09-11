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
        print("=== DUPLICATE PLAYERS SPLIT ENTITY INVESTIGATION ===")
        q = text("""
            SELECT full_name, COUNT(*) as cnt
            FROM players
            GROUP BY full_name
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC;
        """)
        dups = (await conn.execute(q)).fetchall()
        print(f"Total duplicate name groups: {len(dups)}")

        for name, cnt in dups[:15]:
            print(f"\nPlayer Name: '{name}' (Count: {cnt})")
            p_q = text("""
                SELECT 
                    p.player_id, p.gsis_id, p.pfr_id, p.primary_position,
                    p.draft_year, p.draft_round, p.draft_overall, p.rookie_year, p.final_year,
                    (SELECT COUNT(*) FROM player_team_stints s WHERE s.player_id = p.player_id) AS stints_count,
                    (SELECT COUNT(*) FROM accolades a WHERE a.player_id = p.player_id) AS accolades_count
                FROM players p
                WHERE p.full_name = :name;
            """)
            p_rows = (await conn.execute(p_q, {"name": name})).fetchall()
            for row in p_rows:
                print("  ", row)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
