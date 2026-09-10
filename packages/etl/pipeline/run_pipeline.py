import argparse
import asyncio
import datetime
import json
import logging
import os
import sys
from typing import List

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

# Add packages/etl to python path if not present
current_dir = os.path.dirname(os.path.abspath(__file__))
etl_root = os.path.abspath(os.path.join(current_dir, ".."))
if etl_root not in sys.path:
    sys.path.insert(0, etl_root)

from pipeline.extract import NFLDataExtractor
from pipeline.transform import NFLDataTransformer
from pipeline.load import NFLDataLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nfl_etl_runner")


def parse_seasons(seasons_arg: str) -> List[int]:
    """
    Parses comma-separated or range format (e.g., '2020-2024' or '2022,2023,2024').
    """
    if "-" in seasons_arg:
        start_str, end_str = seasons_arg.split("-", 1)
        return list(range(int(start_str), int(end_str) + 1))
    return [int(s.strip()) for s in seasons_arg.split(",") if s.strip()]


async def export_client_search_index(session, out_dir: str = "apps/web/public"):
    """
    Exports the updated player catalog from PostgreSQL to the frontend search index.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_json = os.path.join(out_dir, "player_search_index.json")

    query = text("""
        SELECT player_id, full_name, primary_position, rookie_year, final_year, is_active
        FROM players
        ORDER BY is_active DESC, final_year DESC NULLS FIRST, full_name ASC;
    """)

    result = await session.execute(query)
    rows = result.fetchall()

    player_records = [
        [
            r[0],  # player_id
            r[1],  # full_name
            r[2],  # primary_position
            r[3],  # rookie_year
            r[4],  # final_year
            1 if r[5] else 0,  # is_active
        ]
        for r in rows
    ]

    payload = {
        "version": "2026.09.04.scraped",
        "fields": ["id", "name", "pos", "start", "end", "active"],
        "players": player_records,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))

    logger.info(f"Updated client search index at {out_json} with {len(player_records)} players.")


async def run_pipeline(seasons: List[int], db_url: str):
    logger.info(f"Starting NFL Data Ingestion Pipeline for seasons: {seasons}")
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # Step 1: Seed foundational franchises
        logger.info("Step 1: Ensuring foundational franchises are seeded...")
        await NFLDataLoader.seed_franchises(session)

        # Step 2: Extract raw rosters & ID maps from nflverse
        logger.info(f"Step 2: Extracting rosters for {len(seasons)} seasons...")
        rosters_df = NFLDataExtractor.extract_rosters(seasons)
        logger.info(f"Extracted {len(rosters_df)} raw seasonal roster entries.")

        logger.info("Extracting universal player ID cross-references...")
        id_map_df = NFLDataExtractor.extract_id_mappings()
        logger.info(f"Extracted {len(id_map_df)} ID mappings.")

        # Step 3: Transform & normalize records
        logger.info("Step 3: Transforming and deduplicating player records...")
        players = NFLDataTransformer.transform_players(rosters_df, id_map_df)
        logger.info(f"Transformed into {len(players)} unique canonical players.")

        logger.info("Transforming player franchise stints (enforcing games_played >= 1)...")
        stints = NFLDataTransformer.transform_stints(rosters_df)
        logger.info(f"Transformed into {len(stints)} verified franchise stints.")

        # Step 4: Batch upsert into PostgreSQL
        logger.info("Step 4: Upserting players into PostgreSQL...")
        await NFLDataLoader.upsert_players_batch(session, players)

        logger.info("Upserting player team stints into PostgreSQL...")
        await NFLDataLoader.upsert_stints_batch(session, stints)

        # Step 5: Regenerate search index for client
        logger.info("Step 5: Regenerating client-side player search index...")
        await export_client_search_index(session)

    await engine.dispose()
    logger.info("Pipeline execution completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="NFL Games Data Scraping & Ingestion Pipeline")
    parser.add_argument(
        "--seasons",
        type=str,
        default=f"2000-{datetime.datetime.now().year}",
        help="Seasons to ingest, e.g. '2023,2024' or '2020-2025'"
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=os.getenv("DATABASE_URL", "postgresql+asyncpg://nfl_admin:nfl_dev_secret@localhost:5432/nfl_games_db"),
        help="PostgreSQL async database connection URL"
    )
    args = parser.parse_args()

    seasons = parse_seasons(args.seasons)
    asyncio.run(run_pipeline(seasons, args.db_url))


if __name__ == "__main__":
    main()
