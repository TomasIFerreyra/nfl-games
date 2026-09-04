from datetime import date, datetime
import random
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.schemas.puzzle import DailyPuzzleResponse

router = APIRouter(prefix="/puzzles", tags=["Puzzles"])


@router.get(
    "/{game_type}/daily",
    response_model=DailyPuzzleResponse,
    summary="Fetch sanitized daily puzzle configuration",
)
async def get_daily_puzzle(
    game_type: str,
    target_date: Optional[date] = Query(default=None, alias="date"),
    session: AsyncSession = Depends(get_async_session),
) -> DailyPuzzleResponse:
    """
    Returns the daily puzzle instance for the requested game mode.
    Sanitizes responses so solutions/answers are strictly omitted from client payloads.
    """
    normalized_type = game_type.upper().replace("-", "_")
    valid_types = {"GRID", "REVERSE_GRID", "CONNECTIONS", "TOP10"}
    if normalized_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid game type '{game_type}'. Must be one of: grid, reverse-grid, connections, top10.",
        )

    query_date = target_date or datetime.utcnow().date()

    query = select(DailyPuzzle).where(
        DailyPuzzle.target_date == query_date,
        DailyPuzzle.game_type == normalized_type,
    )
    result = await session.execute(query)
    puzzle = result.scalar_one_or_none()

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
        # Shuffle items and omit group definitions / answers
        items = list(raw_data.get("items", []))
        random.Random(int(query_date.strftime("%Y%m%d"))).shuffle(items)
        sanitized_data = {
            "items": items,
        }
    elif normalized_type == "TOP10":
        # Provide leaderboard slots without revealing player IDs or names
        sanitized_data = {
            "category_id": raw_data.get("category_id"),
            "title": raw_data.get("title"),
            "description": raw_data.get("description"),
            "metric_label": raw_data.get("metric_label"),
            "slots_count": 10,
        }

    return DailyPuzzleResponse(
        puzzle_id=puzzle.puzzle_id,
        puzzle_number=puzzle.puzzle_number,
        target_date=puzzle.target_date,
        game_type=puzzle.game_type.lower(),
        puzzle_data=sanitized_data,
        created_at=puzzle.created_at,
    )
