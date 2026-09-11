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
        print("=== TARGET PLAYERS ROW DETAILS ===")
        r1 = await conn.execute(text("""
            SELECT player_id, gsis_id, pfr_id, full_name, draft_year, draft_round, draft_overall, rookie_year, final_year
            FROM players
            WHERE full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
            ORDER BY full_name, player_id;
        """))
        for row in r1.fetchall():
            print("Player:", row)

        print("\n=== TARGET PLAYERS STINTS ===")
        r2 = await conn.execute(text("""
            SELECT p.player_id, p.full_name, pts.franchise_id, pts.season_year, pts.games_played
            FROM player_team_stints pts
            JOIN players p ON p.player_id = pts.player_id
            WHERE p.full_name IN ('Brett Favre', 'Jordan Love', 'Garrett Wilson')
            ORDER BY p.full_name, pts.season_year;
        """))
        for row in r2.fetchall():
            print("Stint:", row)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
