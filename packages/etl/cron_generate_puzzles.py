#!/usr/bin/env python3
"""
Scheduled Batch Puzzle Generation Pipeline (Cron / Worker).
Generates, validates, solves, and hydrates daily puzzles ahead of time (e.g., D+7 at 00:00:00 UTC).
Ensures SLA <= 120s and guarantees mathematical solvability & density invariants.
"""

import asyncio
from datetime import date, datetime, timedelta
import logging
import os
import sys
import time

# Ensure apps/api and packages/etl are on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
API_DIR = os.path.join(REPO_ROOT, "apps", "api")

if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import click
from redis.asyncio import Redis, ConnectionPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.puzzle_pipeline import PuzzlePipelineService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cron_generate_puzzles")


async def run_batch_generation(days_ahead: int = 7, force: bool = False) -> None:
    """
    Executes the batch generation pipeline for days [D, D+days_ahead].
    """
    pipeline_start = time.perf_counter()
    today = datetime.now().date()
    logger.info(f"Starting batch puzzle generation pipeline for {days_ahead} days ahead (Base: {today})...")

    # 1. Initialize DB and Redis connections
    engine = create_async_engine(
        settings.async_database_url,
        echo=False,
        pool_size=10,
        max_overflow=5,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    redis_pool = None
    redis_client = None
    try:
        redis_pool = ConnectionPool.from_url(
            settings.redis_connection_url,
            max_connections=20,
            decode_responses=True,
            socket_timeout=3.0,
        )
        redis_client = Redis(connection_pool=redis_pool)
        await redis_client.ping()
        logger.info(f"Redis connected at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    except Exception as exc:
        logger.warning(f"Redis not available for batch precomputation: {exc}. Proceeding with DB-only storage.")
        redis_client = None

    generated_count = 0
    skipped_count = 0
    total_days = days_ahead + 1

    try:
        for offset in range(total_days):
            target_date = today + timedelta(days=offset)
            logger.info(f"--- Processing Day +{offset}: {target_date} ---")

            async with session_factory() as session:
                day_start = time.perf_counter()
                puzzle = await PuzzlePipelineService.generate_daily_grid(
                    session=session,
                    target_date=target_date,
                    redis_client=redis_client,
                )
                day_duration = (time.perf_counter() - day_start) * 1000

                raw_data = puzzle.puzzle_data
                cardinalities = raw_data.get("cell_cardinalities", [])
                log_density = raw_data.get("log_density", 0.0)

                logger.info(
                    f"Generated Grid #{puzzle.puzzle_number} for {target_date} in {day_duration:.2f}ms. "
                    f"UUID: {puzzle.puzzle_id}, Log-Density: {log_density}"
                )
                generated_count += 1

    finally:
        if redis_client:
            await redis_client.aclose()
        if redis_pool:
            await redis_pool.disconnect()
        await engine.dispose()

    total_duration = time.perf_counter() - pipeline_start
    logger.info("=" * 60)
    logger.info(
        f"Batch Generation Pipeline Complete in {total_duration:.2f}s "
        f"(SLA Budget: 120s, Status: {'SUCCESS [WITHIN SLA]' if total_duration <= 120 else 'OVER BUDGET'})."
    )
    logger.info(f"Summary: Generated={generated_count}, Skipped={skipped_count}, Total={total_days}")
    logger.info("=" * 60)


@click.command()
@click.option(
    "--days-ahead",
    "-d",
    default=7,
    type=int,
    show_default=True,
    help="Number of future days ahead to generate puzzles for (e.g. 7 for D to D+7).",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force re-generation and overwriting of already published puzzles.",
)
def main(days_ahead: int, force: bool) -> None:
    """Run the batch puzzle generator cron job."""
    asyncio.run(run_batch_generation(days_ahead=days_ahead, force=force))


if __name__ == "__main__":
    main()
