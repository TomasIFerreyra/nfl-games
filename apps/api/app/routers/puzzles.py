import asyncio
from datetime import date, datetime, timezone
import logging
import random
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.schemas.puzzle import DailyPuzzleResponse
from app.services.puzzle_pipeline import PuzzlePipelineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/puzzles", tags=["Puzzles"])


@router.get(
    "/{game_type}/daily",
    response_model=DailyPuzzleResponse,
    summary="Fetch sanitized daily puzzle configuration with JIT auto-generation",
    responses={
        200: {
            "description": "Sanitized daily puzzle configuration.",
            "model": DailyPuzzleResponse,
        },
        400: {
            "description": "Invalid game type requested.",
        },
        404: {
            "description": "Daily puzzle has not been published and auto-generation is disabled.",
        },
    },
)
async def get_daily_puzzle(
    game_type: str,
    target_date: Optional[date] = Query(default=None, alias="date"),
    force_regenerate: bool = Query(default=False, description="Force re-generation of daily puzzle"),
    session: AsyncSession = Depends(get_async_session),
    redis_client: Optional[Redis] = Depends(get_redis),
) -> DailyPuzzleResponse:
    """
    Returns the daily puzzle for the requested game mode:
    1. Queries PostgreSQL / Redis for active puzzle matching target_date (defaults to current UTC date).
    2. If not found and AUTO_GENERATE_MISSING_PUZZLE is enabled:
       - Acquires distributed lock (`puzzle:lock:{game_type}:{target_date}`) to avoid race conditions.
       - Invokes JIT puzzle pipeline compiler to generate, solve, and hydrate puzzle on the fly.
    3. If not found and generation is disabled, returns RFC 7807 404 error.
    4. Sanitizes response so solution sets are strictly omitted from client payloads.
    """
    normalized_type = game_type.upper().replace("-", "_")
    valid_types = {"GRID", "REVERSE_GRID", "CONNECTIONS", "TOP10", "WEDDLE", "GUESS_PLAYER"}
    if normalized_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid game type '{game_type}'. Must be one of: grid, reverse-grid, connections, top10, weddle.",
        )
    if normalized_type == "GUESS_PLAYER":
        normalized_type = "WEDDLE"

    if target_date is not None:
        query_date = target_date
    else:
        query_date = datetime.now(timezone.utc).date()


    puzzle: Optional[DailyPuzzle] = None

    # Check if puzzle already exists
    if not force_regenerate:
        stmt = select(DailyPuzzle).where(
            DailyPuzzle.target_date == query_date,
            DailyPuzzle.game_type == normalized_type,
        )
        result = await session.execute(stmt)
        puzzle = result.scalar_one_or_none()

        # Detect stale/incomplete puzzle: regenerate if solutions are missing or all cells are 0
        if puzzle and not force_regenerate and normalized_type == "GRID":
            raw = puzzle.puzzle_data or {}
            valid_sols = raw.get("valid_solutions", {})
            cell_cards = raw.get("cell_cardinalities", [[0]*3]*3)
            total_card = sum(
                cell_cards[r][c] for r in range(min(3, len(cell_cards)))
                for c in range(min(3, len(cell_cards[r]) if r < len(cell_cards) else 0))
            )
            if not valid_sols or total_card == 0:
                logger.info(
                    f"Stale puzzle detected for {query_date} (total cardinality={total_card}, "
                    f"solutions_present={bool(valid_sols)}). Triggering regeneration."
                )
                puzzle = None  # Force JIT to regenerate

    # If puzzle is missing (or force_regenerate is requested), trigger JIT lazy generation
    if (not puzzle or force_regenerate) and normalized_type in {"GRID", "CONNECTIONS", "TOP10", "WEDDLE"}:
        if settings.AUTO_GENERATE_MISSING_PUZZLE or force_regenerate:
            lock_key = f"puzzle:lock:{normalized_type}:{query_date}"
            lock_token = None
            try:
                # Attempt to acquire distributed lock for JIT compilation
                if redis_client is not None:
                    lock_token = await PuzzlePipelineService.acquire_distributed_lock(
                        redis_client=redis_client,
                        lock_key=lock_key,
                        timeout_secs=settings.PUZZLE_DISTRIBUTED_LOCK_TIMEOUT_SECS,
                    )

                # Inside lock: double-check DB to prevent concurrent generation race
                if not force_regenerate:
                    stmt = select(DailyPuzzle).where(
                        DailyPuzzle.target_date == query_date,
                        DailyPuzzle.game_type == normalized_type,
                    )
                    result = await session.execute(stmt)
                    puzzle = result.scalar_one_or_none()

                if not puzzle or force_regenerate:
                    if normalized_type == "GRID":
                        puzzle = await PuzzlePipelineService.generate_daily_grid(
                            session=session,
                            target_date=query_date,
                            redis_client=redis_client,
                        )
                    elif normalized_type == "CONNECTIONS":
                        puzzle = await PuzzlePipelineService.generate_daily_connections(
                            session=session,
                            target_date=query_date,
                        )
                    elif normalized_type == "TOP10":
                        puzzle = await PuzzlePipelineService.generate_daily_top10(
                            session=session,
                            target_date=query_date,
                        )
                    elif normalized_type == "WEDDLE":
                        puzzle = await PuzzlePipelineService.generate_daily_weddle(
                            session=session,
                            target_date=query_date,
                        )
            finally:
                if lock_token and redis_client is not None:
                    await PuzzlePipelineService.release_distributed_lock(
                        redis_client=redis_client,
                        lock_key=lock_key,
                        lock_token=lock_token,
                    )

    if not puzzle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Daily puzzle for game mode '{game_type}' on date '{query_date}' has not been published.",
        )


    # Sanitize payload based on game type
    raw_data: Dict[str, Any] = puzzle.puzzle_data
    sanitized_data: Dict[str, Any] = {}

    if normalized_type == "GRID":
        sanitized_data = {
            "rows": raw_data.get("rows", []),
            "columns": raw_data.get("columns", []),
            "min_cardinality_guarantee": raw_data.get("min_cardinality_guarantee", 3),
        }
    elif normalized_type == "REVERSE_GRID":
        sanitized_data = {
            "players": raw_data.get("players", []),
            "candidate_criteria": raw_data.get("candidate_criteria", []),
        }
    elif normalized_type == "CONNECTIONS":
        items = list(raw_data.get("items", []))
        random.Random(int(query_date.strftime("%Y%m%d"))).shuffle(items)
        sanitized_data = {
            "items": items,
        }
    elif normalized_type == "TOP10":
        sanitized_data = {
            "category_id": raw_data.get("category_id"),
            "title": raw_data.get("title"),
            "description": raw_data.get("description"),
            "metric_label": raw_data.get("metric_label"),
            "slots_count": 10,
        }
    elif normalized_type == "WEDDLE":
        sanitized_data = {
            "mode": "weddle",
            "max_attempts": 6,
            "attributes_count": 8,
        }


    return DailyPuzzleResponse(
        puzzle_id=puzzle.puzzle_id,
        puzzle_number=puzzle.puzzle_number,
        target_date=puzzle.target_date,
        game_type=puzzle.game_type.lower(),
        puzzle_data=sanitized_data,
        created_at=puzzle.created_at,
    )
