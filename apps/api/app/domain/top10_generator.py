"""
Deterministic Daily NFL Top 10 Puzzle Generator.
Per Section 1.1.4 and Section 4 of SPECIFICATION.md:
- Deterministic seeding with target date: seed = int(target_date.strftime("%Y%m%d")) + 4409.
- Strict archetype family rotation to prevent repetition across consecutive days.
- Resolves 10 ranked slots with tie-breaking, player headshots, and formatted metrics.
- Persists validated puzzle payload into daily_puzzles table with SHA-256 solution_hash.
"""

from datetime import date
import hashlib
import json
import logging
import random
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.puzzle import DailyPuzzle
from app.domain.top10_taxonomy import (
    Top10Archetype,
    Top10CategoryDefinition,
    resolve_category_leaderboard,
    top10_registry,
)
from app.schemas.top10 import Top10Entry, Top10PuzzleData

logger = logging.getLogger(__name__)


class Top10Generator:
    """
    Deterministic generator for daily NFL Top 10 leaderboard puzzles.
    """

    @classmethod
    def get_seed_for_date(cls, target_date: date) -> int:
        """Computes deterministic seed based on target calendar date."""
        return int(target_date.strftime("%Y%m%d")) + 4409

    @classmethod
    def compute_solution_hash(cls, payload: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash for puzzle verification."""
        canonical_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    @classmethod
    def select_category_for_date(cls, target_date: date) -> Top10CategoryDefinition:
        """
        Selects a category deterministically, rotating archetype families to prevent repetition.
        """
        seed = cls.get_seed_for_date(target_date)
        rng = random.Random(seed)

        archetype_cycle = [
            Top10Archetype.SINGLE_SEASON_MILESTONE,
            Top10Archetype.CHRONOLOGICAL_ACCOLADE,
            Top10Archetype.RECENT_DRAFT_PEDIGREE,
            Top10Archetype.ALL_TIME_HISTORICAL_LEADERBOARD,
        ]

        # Determine archetype from calendar day index
        day_index = (target_date.toordinal()) % len(archetype_cycle)
        chosen_archetype = archetype_cycle[day_index]

        candidate_categories = top10_registry.get_by_archetype(chosen_archetype)
        if not candidate_categories:
            candidate_categories = top10_registry.get_all()

        return rng.choice(candidate_categories)

    @classmethod
    async def generate_puzzle_data(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
    ) -> Dict[str, Any]:
        """
        Generates and validates the complete Top 10 puzzle data dictionary for target date.
        """
        category = cls.select_category_for_date(target_date)
        leaderboard_entries: List[Top10Entry] = await resolve_category_leaderboard(
            session=session,
            category=category,
        )

        leaderboard_dicts = [
            {
                "rank": e.rank,
                "player_id": e.player_id,
                "player_name": e.player_name,
                "metric_value": e.metric_value,
                "formatted_value": e.formatted_value,
                "headshot_url": e.headshot_url,
                "active_years": e.active_years,
                "primary_franchise": e.primary_franchise,
                "tied_player_ids": e.tied_player_ids or [],
            }
            for e in leaderboard_entries
        ]

        puzzle_data = {
            "category_id": category.category_id,
            "title": category.title,
            "description": category.description,
            "metric_label": category.metric_label,
            "slots_count": 10,
            "leaderboard": leaderboard_dicts,
        }

        return puzzle_data

    @classmethod
    async def generate_and_publish_daily_puzzle(
        cls,
        session: AsyncSession,
        target_date: date,
        puzzle_number: int,
    ) -> Dict[str, Any]:
        """
        Generates, validates, hashes, and stores the daily Top 10 puzzle into PostgreSQL / SQLite.
        """
        puzzle_data = await cls.generate_puzzle_data(
            session=session,
            target_date=target_date,
            puzzle_number=puzzle_number,
        )

        sol_hash = cls.compute_solution_hash(puzzle_data)

        stmt = select(DailyPuzzle).where(
            DailyPuzzle.target_date == target_date,
            DailyPuzzle.game_type == "TOP10",
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.puzzle_data = puzzle_data
            existing.solution_hash = sol_hash
            existing.puzzle_number = puzzle_number
        else:
            puzzle = DailyPuzzle(
                puzzle_id=uuid.uuid4(),
                target_date=target_date,
                game_type="TOP10",
                puzzle_number=puzzle_number,
                puzzle_data=puzzle_data,
                solution_hash=sol_hash,
            )
            session.add(puzzle)

        await session.commit()
        logger.info(f"Published Top 10 puzzle #{puzzle_number} for {target_date} ({puzzle_data['title']}).")

        return puzzle_data
