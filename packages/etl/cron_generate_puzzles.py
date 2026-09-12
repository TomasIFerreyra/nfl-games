#!/usr/bin/env python3
"""
Scheduled Batch Puzzle Generation Pipeline (Cron / Worker).
Generates, validates, solves, and hydrates daily puzzles ahead of time for all game modes:
GRID, CONNECTIONS, TOP10, and WEDDLE.
Strictly idempotent: preserves existing active games unless explicitly run with --force.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
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
from redis.asyncio import ConnectionPool, Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models.puzzle import DailyPuzzle
from app.services.puzzle_pipeline import PuzzlePipelineService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cron_generate_puzzles")


async def run_batch_generation(days_ahead: int = 7, force: bool = False) -> None:
    """
    Executes the batch generation pipeline for days [D, D+days_ahead] across all game modes.
    """
    pipeline_start = time.perf_counter()
    today = datetime.now(timezone.utc).date()
    logger.info(f"Starting batch puzzle generation for {days_ahead} days ahead (Base UTC: {today})...")

    # 1. Initialize DB and Redis connections
    engine = create_async_engine(
        settings.async_database_url,
        echo=False,
        pool_size=5,
        max_overflow=2,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    redis_pool = None
    redis_client = None
    try:
        redis_pool = ConnectionPool.from_url(
            settings.redis_connection_url,
            max_connections=10,
            decode_responses=True,
            socket_timeout=3.0,
        )
        redis_client = Redis(connection_pool=redis_pool)
        await redis_client.ping()
        logger.info("Redis connected successfully for batch precomputation.")
    except Exception as exc:
        logger.warning(f"Redis not available for batch precomputation: {exc}. Proceeding with DB-only storage.")
        redis_client = None

    stats = {"generated": 0, "skipped": 0, "failed": 0}
    game_modes = ["GRID", "CONNECTIONS", "TOP10", "WEDDLE"]
    total_days = days_ahead + 1

    try:
        for offset in range(total_days):
            target_date = today + timedelta(days=offset)
            logger.info(f"=== Processing Date: {target_date} (+{offset}d) ===")

            for mode in game_modes:
                async with session_factory() as session:
                    # 1. Idempotency Check: Verify if puzzle already exists
                    stmt = select(DailyPuzzle).where(
                        DailyPuzzle.target_date == target_date,
                        DailyPuzzle.game_type == mode,
                    )
                    existing = (await session.execute(stmt)).scalar_one_or_none()

                    if existing and not force:
                        logger.info(f"  [{mode}] Puzzle already exists (ID: {existing.puzzle_id}). Skipping.")
                        stats["skipped"] += 1
                        continue

                    # 2. Generate and persist puzzle
                    try:
                        t0 = time.perf_counter()
                        if mode == "GRID":
                            puzzle = await PuzzlePipelineService.generate_daily_grid(
                                session=session,
                                target_date=target_date,
                                redis_client=redis_client,
                            )
                        elif mode == "CONNECTIONS":
                            puzzle = await PuzzlePipelineService.generate_daily_connections(
                                session=session,
                                target_date=target_date,
                            )
                        elif mode == "TOP10":
                            puzzle = await PuzzlePipelineService.generate_daily_top10(
                                session=session,
                                target_date=target_date,
                            )
                        elif mode == "WEDDLE":
                            puzzle = await PuzzlePipelineService.generate_daily_weddle(
                                session=session,
                                target_date=target_date,
                            )
                        elapsed_ms = (time.perf_counter() - t0) * 1000
                        logger.info(
                            f"  [{mode}] Generated successfully in {elapsed_ms:.2f}ms (UUID: {puzzle.puzzle_id})."
                        )
                        stats["generated"] += 1
                    except Exception as exc:
                        await session.rollback()
                        logger.error(f"  [{mode}] Generation failed for {target_date}: {exc}", exc_info=True)
                        stats["failed"] += 1

    finally:
        if redis_client:
            await redis_client.aclose()
        if redis_pool:
            await redis_pool.disconnect()
        await engine.dispose()

    total_duration = time.perf_counter() - pipeline_start
    logger.info("=" * 60)
    logger.info(f"Batch Generation Pipeline Complete in {total_duration:.2f}s")
    logger.info(
        f"Summary: Generated={stats['generated']}, Skipped={stats['skipped']}, Failed={stats['failed']}"
    )
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

