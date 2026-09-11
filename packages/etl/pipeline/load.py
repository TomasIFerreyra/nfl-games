import logging
from typing import Any, Dict, List
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Default foundational NFL franchises
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


class NFLDataLoader:
    """
    Executes idempotent bulk UPSERT operations into PostgreSQL tables.
    """

    @classmethod
    async def seed_franchises(cls, session: AsyncSession) -> None:
        """
        Seeds foundational NFL franchise entries.
        """
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
        logger.info(f"Seeded {len(FOUNDATIONAL_FRANCHISES)} NFL franchises.")

    @classmethod
    async def upsert_players_batch(cls, session: AsyncSession, players: List[Dict[str, Any]]) -> None:
        """
        Bulk upsert for players on conflict with gsis_id.
        """
        if not players:
            return

        stmt = text("""
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
            ON CONFLICT (gsis_id) DO UPDATE SET
                pfr_id = COALESCE(EXCLUDED.pfr_id, players.pfr_id),
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

        # Execute in chunks of 500
        chunk_size = 500
        for i in range(0, len(players), chunk_size):
            chunk = players[i : i + chunk_size]
            await session.execute(stmt, chunk)
        await session.commit()
        logger.info(f"Upserted {len(players)} player records.")

    @classmethod
    async def upsert_stints_batch(cls, session: AsyncSession, stints: List[Dict[str, Any]]) -> None:
        """
        Bulk upsert for player franchise stints with games_played >= 1.
        """
        if not stints:
            return

        stmt = text("""
            INSERT INTO player_team_stints (
                player_id, franchise_id, season_year, games_played, games_started
            )
            SELECT 
                p.player_id, :franchise_id, :season_year, :games_played, :games_started
            FROM players p
            WHERE p.gsis_id = :gsis_id
            ON CONFLICT (player_id, franchise_id, season_year) DO UPDATE SET
                games_played = EXCLUDED.games_played,
                games_started = EXCLUDED.games_started;
        """)

        chunk_size = 500
        for i in range(0, len(stints), chunk_size):
            chunk = stints[i : i + chunk_size]
            await session.execute(stmt, chunk)
        await session.commit()
        logger.info(f"Upserted {len(stints)} player team stints.")
