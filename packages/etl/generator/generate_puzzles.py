from datetime import date, datetime
import hashlib
import json
import logging
import math
import random
from typing import Any, Dict, List, Tuple
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DailyPuzzleGenerator:
    """
    Deterministic daily puzzle generator enforcing solvability and balance invariants.
    """

    @classmethod
    def compute_solution_hash(cls, payload: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash for puzzle verification."""
        canonical_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    async def generate_grid_puzzle(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
        k_min: int = 3,
    ) -> Dict[str, Any]:
        """
        Generates a 3x3 Grid puzzle for the target date guaranteeing |R_r ∩ C_c| >= k_min.
        """
        # Use dynamic procedural grid generation engine
        from packages.etl.generator.grid_generator import GridGenerator

        puzzle_data = await GridGenerator.generate_puzzle_data(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
            k_min=k_min,
        )

        sol_hash = cls.compute_solution_hash(puzzle_data)

        # Store in daily_puzzles table
        insert_stmt = text("""
            INSERT INTO daily_puzzles (target_date, game_type, puzzle_number, puzzle_data, solution_hash)
            VALUES (:target_date, 'GRID', :puzzle_number, :puzzle_data, :solution_hash)
            ON CONFLICT (target_date, game_type) DO UPDATE SET
                puzzle_data = EXCLUDED.puzzle_data,
                solution_hash = EXCLUDED.solution_hash;
        """)

        await session.execute(insert_stmt, {
            "target_date": target_date,
            "puzzle_number": puzzle_number,
            "puzzle_data": json.dumps(puzzle_data),
            "solution_hash": sol_hash,
        })
        await session.commit()
        logger.info(f"Published Grid puzzle #{puzzle_number} for {target_date}.")
        return puzzle_data

    @classmethod
    async def generate_connections_puzzle(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
    ) -> Dict[str, Any]:
        """
        Generates and publishes a daily Connections 4x4 puzzle using Knuth's Algorithm X validation.
        """
        from packages.etl.generator.connections_generator import ConnectionsGenerator

        return await ConnectionsGenerator.generate_and_publish_daily_puzzle(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
        )

    @classmethod
    async def generate_top10_puzzle(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
    ) -> Dict[str, Any]:
        """
        Generates and publishes a daily Top 10 Leaderboard puzzle.
        """
        from packages.etl.generator.top10_generator import Top10Generator

        return await Top10Generator.generate_and_publish_daily_puzzle(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
        )

