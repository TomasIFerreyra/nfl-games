#!/usr/bin/env python3
"""
Utility runner for SQL scripts using project database connection settings.
"""

import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.join(CURRENT_DIR, "..", "apps", "api")
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

from app.core.config import settings

async def run_sql_file(file_path: str):
    abs_path = os.path.abspath(file_path)
    if not os.path.isfile(abs_path):
        print(f"Error: File '{abs_path}' does not exist.")
        sys.exit(1)

    print(f"Reading SQL script: {abs_path}")
    with open(abs_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    print(f"Connecting to database: {settings.async_database_url}")
    engine = create_async_engine(settings.async_database_url, isolation_level="AUTOCOMMIT")

    async with engine.connect() as conn:
        # Split statements by semicolon while ignoring comments and blocks
        # Execute raw script or transaction blocks
        raw_conn = await conn.get_raw_connection()
        # Using asyncpg driver under SQLAlchemy
        asyncpg_conn = raw_conn.driver_connection
        result = await asyncpg_conn.execute(sql_content)
        print("Execution result:", result)

    await engine.dispose()
    print("SQL script completed successfully.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_sql_script.py <path_to_sql_file>")
        sys.exit(1)
    asyncio.run(run_sql_file(sys.argv[1]))
