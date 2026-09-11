import asyncio
import json
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://nfl_admin:nfl_dev_secret@localhost:5432/nfl_games_db")

FOUNDATIONAL_FRANCHISES = [
    {"franchise_id": "ARI", "canonical_name": "Arizona Cardinals", "established_year": 1920},
    {"franchise_id": "ATL", "canonical_name": "Atlanta Falcons", "established_year": 1966},
    {"franchise_id": "BAL", "canonical_name": "Baltimore Ravens", "established_year": 1996},
    {"franchise_id": "BUF", "canonical_name": "Buffalo Bills", "established_year": 1960},
    {"franchise_id": "CAR", "canonical_name": "Carolina Panthers", "established_year": 1995},
    {"franchise_id": "CHI", "canonical_name": "Chicago Bears", "established_year": 1920},
    {"franchise_id": "CIN", "canonical_name": "Cincinnati Bengals", "established_year": 1968},
    {"franchise_id": "CLE", "canonical_name": "Cleveland Browns", "established_year": 1946},
    {"franchise_id": "DAL", "canonical_name": "Dallas Cowboys", "established_year": 1960},
    {"franchise_id": "DEN", "canonical_name": "Denver Broncos", "established_year": 1960},
    {"franchise_id": "DET", "canonical_name": "Detroit Lions", "established_year": 1930},
    {"franchise_id": "GNB", "canonical_name": "Green Bay Packers", "established_year": 1921},
    {"franchise_id": "HOU", "canonical_name": "Houston Texans", "established_year": 2002},
    {"franchise_id": "IND", "canonical_name": "Indianapolis Colts", "established_year": 1953},
    {"franchise_id": "JAX", "canonical_name": "Jacksonville Jaguars", "established_year": 1995},
    {"franchise_id": "KC",  "canonical_name": "Kansas City Chiefs", "established_year": 1960},
    {"franchise_id": "LAC", "canonical_name": "Los Angeles Chargers", "established_year": 1960},
    {"franchise_id": "LAR", "canonical_name": "Los Angeles Rams", "established_year": 1937},
    {"franchise_id": "LVR", "canonical_name": "Las Vegas Raiders", "established_year": 1960},
    {"franchise_id": "MIA", "canonical_name": "Miami Dolphins", "established_year": 1966},
    {"franchise_id": "MIN", "canonical_name": "Minnesota Vikings", "established_year": 1961},
    {"franchise_id": "NE",  "canonical_name": "New England Patriots", "established_year": 1960},
    {"franchise_id": "NOR", "canonical_name": "New Orleans Saints", "established_year": 1967},
    {"franchise_id": "NYG", "canonical_name": "New York Giants", "established_year": 1925},
    {"franchise_id": "NYJ", "canonical_name": "New York Jets", "established_year": 1960},
    {"franchise_id": "PHI", "canonical_name": "Philadelphia Eagles", "established_year": 1933},
    {"franchise_id": "PIT", "canonical_name": "Pittsburgh Steelers", "established_year": 1933},
    {"franchise_id": "SEA", "canonical_name": "Seattle Seahawks", "established_year": 1976},
    {"franchise_id": "SFO", "canonical_name": "San Francisco 49ers", "established_year": 1946},
    {"franchise_id": "TAM", "canonical_name": "Tampa Bay Buccaneers", "established_year": 1976},
    {"franchise_id": "TEN", "canonical_name": "Tennessee Titans", "established_year": 1960},
    {"franchise_id": "WAS", "canonical_name": "Washington Commanders", "established_year": 1932},
]

async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        stmt_franchise = text("""
            INSERT INTO franchises (franchise_id, canonical_name, established_year)
            VALUES (:franchise_id, :canonical_name, :established_year)
            ON CONFLICT (franchise_id) DO UPDATE SET
                canonical_name = EXCLUDED.canonical_name,
                established_year = EXCLUDED.established_year;
        """)
        for item in FOUNDATIONAL_FRANCHISES:
            await session.execute(stmt_franchise, item)
        await session.commit()
        print(f"Seeded {len(FOUNDATIONAL_FRANCHISES)} franchises.")

        index_path = os.path.join("apps", "web", "public", "player_search_index.json")
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        stmt_player = text("""
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
                full_name = EXCLUDED.full_name,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                primary_position = EXCLUDED.primary_position,
                rookie_year = EXCLUDED.rookie_year,
                final_year = EXCLUDED.final_year,
                is_active = EXCLUDED.is_active;
        """)

        player_params = []
        for raw in data.get("players", []):
            p_id, name, pos, start_yr, end_yr, active = raw[0], raw[1], raw[2], raw[3], raw[4], bool(raw[5])
            parts = name.split(" ")
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else parts[0]
            gsis_id = p_id if p_id.startswith("00-") else None
            pfr_id = p_id[:40] if p_id.startswith("p-") else None
            player_params.append({
                "player_id": p_id,
                "gsis_id": gsis_id,
                "pfr_id": pfr_id,
                "full_name": name,
                "first_name": first_name,
                "last_name": last_name,
                "primary_position": pos,
                "draft_year": start_yr,
                "draft_round": None,
                "draft_overall": None,
                "college": None,
                "rookie_year": start_yr,
                "final_year": end_yr,
                "is_active": active,
                "headshot_url": None,
            })

        chunk_size = 500
        for i in range(0, len(player_params), chunk_size):
            chunk = player_params[i : i + chunk_size]
            await session.execute(stmt_player, chunk)
        await session.commit()
        print(f"Seeded {len(player_params)} players.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
