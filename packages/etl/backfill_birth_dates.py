#!/usr/bin/env python3
"""
backfill_birth_dates.py
-----------------------
Idempotent ETL script to backfill canonical `birth_date` (DATE) for all active and
historical NFL players in PostgreSQL using nflverse / nflreadpy / nfl_data_py data sources.

Eliminates static integer age persistence across the platform by establishing
the canonical birth date single-source-of-truth.
"""

import argparse
import asyncio
import datetime
from datetime import date, datetime as dt
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Path resolution for standalone or submodule execution
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "apps", "api"))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

try:
    from app.core.config import settings
except ImportError:
    settings = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_birth_dates")


def parse_birth_date(raw: Any) -> Optional[date]:
    """
    Robustly parses diverse birth date string representations and formats into a Python date.
    Handles:
    - 'YYYY-MM-DD'
    - 'MM/DD/YYYY'
    - 'YYYY/MM/DD'
    - 'YYYY-MM-DDTHH:MM:SS'
    - Pandas Timestamp / datetime objects
    - Null / NaN / Empty strings
    """
    if raw is None or pd.isna(raw):
        return None

    if isinstance(raw, (date, dt)):
        if isinstance(raw, dt):
            parsed = raw.date()
        else:
            parsed = raw
        if 1900 <= parsed.year <= date.today().year:
            return parsed
        return None

    raw_str = str(raw).strip()
    if not raw_str or raw_str.lower() in ("nan", "none", "nat", "null", ""):
        return None

    # Strip any ISO timestamp portion
    if "t" in raw_str.lower():
        raw_str = re.split(r"[tT\s]", raw_str)[0].strip()

    # Try common explicit date formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            parsed = dt.strptime(raw_str, fmt).date()
            if 1900 <= parsed.year <= date.today().year:
                return parsed
        except ValueError:
            continue

    # Fallback to pandas to_datetime
    try:
        ts = pd.to_datetime(raw_str, errors="coerce")
        if pd.notna(ts):
            parsed = ts.date()
            if 1900 <= parsed.year <= date.today().year:
                return parsed
    except Exception:
        pass

    return None


def fetch_nflverse_player_roster() -> pd.DataFrame:
    """
    Fetches official player directory from nflreadpy / nfl_data_py or nflverse GitHub release.
    Guarantees retrieval of birth_date / dob metadata across historical and active players.
    """
    # 1. Try nflreadpy
    try:
        import nflreadpy as nfl
        logger.info("Ingesting players via nflreadpy.load_players()...")
        df = nfl.load_players()
        return df.to_pandas() if hasattr(df, "to_pandas") else df
    except Exception as exc:
        logger.warning(f"nflreadpy load failed ({exc}); trying nfl_data_py...")

    # 2. Try nfl_data_py
    try:
        import nfl_data_py as nfl_data
        logger.info("Ingesting players via nfl_data_py.import_players()...")
        df = nfl_data.import_players()
        return df
    except Exception as exc:
        logger.warning(f"nfl_data_py import failed ({exc}); downloading direct from nflverse release...")

    # 3. Direct CSV from nflverse GitHub data release
    url = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
    logger.info(f"Downloading player catalog from {url}...")
    df = pd.read_csv(url, low_memory=False)
    return df


async def stage_and_backfill_birth_dates(
    session: AsyncSession,
    raw_data: List[Dict[str, Any]],
    chunk_size: int = 500,
) -> Tuple[int, int]:
    """
    Stages raw player birth date data into a temporary table and performs
    an idempotent bulk UPDATE against the PostgreSQL players table.
    """
    if not raw_data:
        return 0, 0

    # 1. Create temporary staging table
    await session.execute(text("""
        CREATE TEMP TABLE IF NOT EXISTS raw_player_data (
            gsis_id VARCHAR(50),
            pfr_id VARCHAR(50),
            full_name VARCHAR(100),
            birth_date DATE
        ) ON COMMIT DROP;
    """))
    await session.execute(text("TRUNCATE TABLE raw_player_data;"))

    # 2. Insert records into staging table in chunks
    insert_staging_sql = text("""
        INSERT INTO raw_player_data (gsis_id, pfr_id, full_name, birth_date)
        VALUES (:gsis_id, :pfr_id, :full_name, :birth_date);
    """)

    for i in range(0, len(raw_data), chunk_size):
        chunk = raw_data[i : i + chunk_size]
        await session.execute(insert_staging_sql, chunk)

    # 3. Create staging indexes for optimal join performance
    await session.execute(text("CREATE INDEX IF NOT EXISTS idx_tmp_raw_gsis ON raw_player_data(gsis_id);"))
    await session.execute(text("CREATE INDEX IF NOT EXISTS idx_tmp_raw_pfr ON raw_player_data(pfr_id);"))
    await session.execute(text("CREATE INDEX IF NOT EXISTS idx_tmp_raw_name ON raw_player_data(full_name);"))

    # 4. Primary Idempotent Update: Match by gsis_id
    stmt_update_gsis = text("""
        UPDATE players p
        SET birth_date = r.birth_date
        FROM raw_player_data r
        WHERE p.gsis_id = r.gsis_id 
          AND r.birth_date IS NOT NULL
          AND (p.birth_date IS NULL OR p.birth_date <> r.birth_date);
    """)
    res_gsis = await session.execute(stmt_update_gsis)
    gsis_updated = res_gsis.rowcount or 0
    logger.info(f"Updated {gsis_updated} player birth dates matching on gsis_id.")

    # 5. Secondary Idempotent Update: Match by pfr_id for players without gsis_id or still null
    stmt_update_pfr = text("""
        UPDATE players p
        SET birth_date = r.birth_date
        FROM raw_player_data r
        WHERE p.pfr_id = r.pfr_id 
          AND r.birth_date IS NOT NULL
          AND (p.birth_date IS NULL OR p.birth_date <> r.birth_date);
    """)
    res_pfr = await session.execute(stmt_update_pfr)
    pfr_updated = res_pfr.rowcount or 0
    logger.info(f"Updated {pfr_updated} player birth dates matching on pfr_id.")

    # 6. Tertiary Idempotent Update: Match by normalized full_name where still null
    stmt_update_name = text("""
        UPDATE players p
        SET birth_date = r.birth_date
        FROM raw_player_data r
        WHERE LOWER(TRIM(p.full_name)) = LOWER(TRIM(r.full_name))
          AND p.birth_date IS NULL
          AND r.birth_date IS NOT NULL;
    """)
    res_name = await session.execute(stmt_update_name)
    name_updated = res_name.rowcount or 0
    logger.info(f"Updated {name_updated} player birth dates matching on full_name.")

    await session.commit()
    total_updated = gsis_updated + pfr_updated + name_updated
    return len(raw_data), total_updated


async def run_backfill(db_url: Optional[str] = None) -> None:
    """Orchestrates loading, cleaning, staging, and backfilling birth dates."""
    conn_url = (
        db_url
        or (settings.async_database_url if settings else None)
        or os.getenv("DATABASE_URL")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/nfl_games"
    )

    if "asyncpg" not in conn_url and conn_url.startswith("postgresql://"):
        conn_url = conn_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(
        conn_url,
        echo=False,
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    df_raw = fetch_nflverse_player_roster()
    logger.info(f"Total raw players ingested from provider: {len(df_raw)}")

    # Detect birth date column
    dob_col = None
    for candidate in ("birth_date", "dob", "birthdate", "player_birth_date"):
        if candidate in df_raw.columns:
            dob_col = candidate
            break

    if not dob_col:
        raise ValueError(f"Could not locate birth_date column in raw dataset. Available: {list(df_raw.columns)}")

    logger.info(f"Using '{dob_col}' as provider birth date source column.")

    # Clean and structure payload
    staged_records: List[Dict[str, Any]] = []
    valid_dates_count = 0

    for _, row in df_raw.iterrows():
        b_date = parse_birth_date(row.get(dob_col))
        if b_date is not None:
            valid_dates_count += 1

        g_id = str(row.get("gsis_id", "")).strip() if pd.notna(row.get("gsis_id")) else None
        p_id = str(row.get("pfr_id", "")).strip() if pd.notna(row.get("pfr_id")) else None
        name = str(row.get("display_name", "") or row.get("full_name", "")).strip()

        if b_date and (g_id or p_id or name):
            staged_records.append({
                "gsis_id": g_id,
                "pfr_id": p_id,
                "full_name": name,
                "birth_date": b_date,
            })

    logger.info(
        f"Parsed {valid_dates_count} valid birth dates out of {len(df_raw)} records. "
        f"Prepared {len(staged_records)} staged records for SQL UPSERT."
    )

    async with session_factory() as session:
        staged_cnt, updated_cnt = await stage_and_backfill_birth_dates(session, staged_records)
        logger.info(f"Successfully processed {staged_cnt} staged items; {updated_cnt} database records modified.")

    await engine.dispose()
    logger.info("Backfill birth_dates execution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill canonical birth_date in players table.")
    parser.add_argument("--db-url", type=str, help="PostgreSQL async database URL")
    args = parser.parse_args()

    asyncio.run(run_backfill(db_url=args.db_url))
