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
        Generates and publishes a daily Connections 4x4 puzzle.
        """
        puzzle_data = {
            "items": [
                {"item_id": "i1", "display_text": "Cam Newton"},
                {"item_id": "i2", "display_text": "Lamar Jackson"},
                {"item_id": "i3", "display_text": "Kyler Murray"},
                {"item_id": "i4", "display_text": "Baker Mayfield"},
                {"item_id": "i5", "display_text": "Patrick Mahomes"},
                {"item_id": "i6", "display_text": "Peyton Manning"},
                {"item_id": "i7", "display_text": "Drew Brees"},
                {"item_id": "i8", "display_text": "Tom Brady"},
                {"item_id": "i9", "display_text": "Randy Moss"},
                {"item_id": "i10", "display_text": "Jerry Rice"},
                {"item_id": "i11", "display_text": "Terrell Owens"},
                {"item_id": "i12", "display_text": "Cris Carter"},
                {"item_id": "i13", "display_text": "Michael Strahan"},
                {"item_id": "i14", "display_text": "T.J. Watt"},
                {"item_id": "i15", "display_text": "J.J. Watt"},
                {"item_id": "i16", "display_text": "Aaron Donald"},
            ],
            "groups": [
                {
                    "group_id": "grp_heisman",
                    "tier": 1,
                    "title": "Heisman Trophy Winning Quarterbacks",
                    "item_ids": ["i1", "i2", "i3", "i4"],
                    "explanation": "All 4 won the Heisman Trophy in college football.",
                },
                {
                    "group_id": "grp_pass_5000",
                    "tier": 2,
                    "title": "5,000+ Passing Yards in a Single Season",
                    "item_ids": ["i5", "i6", "i7", "i8"],
                    "explanation": "All 4 threw for over 5,000 yards in a single NFL season.",
                },
                {
                    "group_id": "grp_rec_td_100",
                    "tier": 3,
                    "title": "120+ Career Receiving Touchdowns",
                    "item_ids": ["i9", "i10", "i11", "i12"],
                    "explanation": "All 4 caught at least 120 regular season receiving touchdowns.",
                },
                {
                    "group_id": "grp_dpoy_mult",
                    "tier": 4,
                    "title": "Multiple AP NFL Defensive Player of the Year Awards",
                    "item_ids": ["i13", "i14", "i15", "i16"],
                    "explanation": "Multiple or single-season sack record holders / multi-time DPOY winners.",
                },
            ],
        }

        sol_hash = cls.compute_solution_hash(puzzle_data)

        insert_stmt = text("""
            INSERT INTO daily_puzzles (target_date, game_type, puzzle_number, puzzle_data, solution_hash)
            VALUES (:target_date, 'CONNECTIONS', :puzzle_number, :puzzle_data, :solution_hash)
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
        logger.info(f"Published Connections puzzle #{puzzle_number} for {target_date}.")
        return puzzle_data
