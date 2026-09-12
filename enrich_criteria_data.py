#!/usr/bin/env python3
"""
Standalone Idempotent Data Enrichment & Criteria Coverage CLI.
Enriches draft picks, colleges, hardware accolades, and career statistics,
and executes coverage verification across PostgreSQL.
"""

import asyncio
import logging
import os
import sys
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "apps", "api")
ETL_DIR = os.path.join(CURRENT_DIR, "packages", "etl")

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if ETL_DIR not in sys.path:
    sys.path.insert(0, ETL_DIR)

import click
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.domain.criteria_registry import registry
from packages.etl.pipeline.data_enrichment import DataEnrichmentService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("enrich_criteria_data")


async def run_enrichment(min_coverage: int = 50, dry_run: bool = False) -> None:
    start_time = time.perf_counter()
    logger.info("Starting NFL Criteria Data Enrichment Pipeline...")

    engine = create_async_engine(
        settings.async_database_url,
        echo=False,
        pool_size=10,
        max_overflow=5,
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            # 1. Enrich Draft Picks & Colleges
            logger.info("Step 1/4: Enriching Draft and College records...")
            draft_count = await DataEnrichmentService.enrich_draft_and_colleges(session)

            # 2. Enrich Hardware Accolades
            logger.info("Step 2/4: Enriching Hardware Accolades...")
            acc_count = await DataEnrichmentService.enrich_accolades(session)

            # 3. Compute Career Stats Aggregates
            logger.info("Step 3/4: Computing Precomputed Career Statistics...")
            career_count = await DataEnrichmentService.compute_career_stats(session)

            # 4. Validate Criteria Coverage
            logger.info(f"Step 4/4: Validating Criteria Coverage (Threshold >= {min_coverage})...")
            coverage_report = await DataEnrichmentService.validate_criteria_coverage(
                session=session,
                custom_registry=registry,
                min_threshold=min_coverage,
            )

            logger.info("=" * 60)
            logger.info(f"Enrichment Complete in {time.perf_counter() - start_time:.2f}s")
            logger.info(f" - Draft/College records updated: {draft_count}")
            logger.info(f" - Accolades inserted: {acc_count}")
            logger.info(f" - Career Stats computed: {career_count}")
            logger.info(f" - Active Criteria: {coverage_report['active_criteria']}/{coverage_report['total_criteria']}")
            logger.info(f" - Deactivated Criteria: {coverage_report['deactivated_criteria']}")
            logger.info("=" * 60)

    finally:
        await engine.dispose()


@click.command()
@click.option(
    "--min-coverage",
    "-c",
    default=50,
    type=int,
    show_default=True,
    help="Minimum qualifying player count required to mark a criterion active in the generator.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run in dry-run mode without modifying records.",
)
def main(min_coverage: int, dry_run: bool) -> None:
    """Run the criteria data enrichment and coverage validation script."""
    asyncio.run(run_enrichment(min_coverage=min_coverage, dry_run=dry_run))


if __name__ == "__main__":
    main()
