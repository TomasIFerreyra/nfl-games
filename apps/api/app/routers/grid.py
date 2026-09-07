import logging
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.session import get_async_session
from app.schemas.grid import GridValidateRequest, GridValidateResponse
from app.services.grid_precompute_service import GridPrecomputeService
from app.services.grid_validation_service import GridValidationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grid", tags=["3x3 Grid"])


@router.post(
    "/validate",
    response_model=GridValidateResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate 3x3 Grid cell guess with O(1) Redis membership and Bayesian rarity scoring",
    responses={
        200: {
            "description": "Validation result containing membership status, rarity score, and pick counts.",
            "model": GridValidateResponse,
        },
        400: {
            "description": "Invalid grid coordinates or parameters.",
        },
        404: {
            "description": "Puzzle ID not found or game type mismatch.",
        },
        422: {
            "description": "Unprocessable entity / schema validation failure.",
        },
    },
)
async def validate_grid_guess(
    payload: GridValidateRequest,
    session: AsyncSession = Depends(get_async_session),
    redis_client: Optional[Redis] = Depends(get_redis),
) -> GridValidateResponse:
    """
    Sub-15ms validation endpoint for 3x3 Daily Grid guesses:
    1. Validates coordinate boundaries (r in [0, 2], c in [0, 2]).
    2. Performs O(1) Redis Set membership check against precomputed solution sets (`SISMEMBER`).
    3. Seamlessly fails over to PostgreSQL JSONB if Redis is offline or key is unpopulated.
    4. On valid match, atomically increments submission counters and computes smoothed Bayesian rarity:
       R*(p, c) = [(n(p, c) + M * pi(p, c)) / (N(c) + M)] * 100
    5. Asynchronously buffers/syncs aggregate stats into PostgreSQL `aggregated_answer_stats`.
    """
    if payload.row_index < 0 or payload.row_index > 2 or payload.col_index < 0 or payload.col_index > 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grid coordinates (row_index, col_index) must be within range [0, 2].",
        )

    try:
        response = await GridValidationService.validate_guess(
            session=session,
            puzzle_id=payload.puzzle_id,
            row_index=payload.row_index,
            col_index=payload.col_index,
            player_id=payload.player_id,
            redis_client=redis_client,
        )
        return response
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Unexpected error during grid validation: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while validating grid guess.",
        )


@router.post(
    "/{puzzle_id}/precompute",
    summary="Execute offline relational precomputation for all 9 cells of a Grid puzzle",
    status_code=status.HTTP_200_OK,
)
async def precompute_puzzle(
    puzzle_id: str,
    session: AsyncSession = Depends(get_async_session),
    redis_client: Optional[Redis] = Depends(get_redis),
) -> Dict[str, Any]:
    """
    Cron / Worker endpoint to execute the relational intersection queries ONCE for all 9 cells (r, c),
    store the precomputed solution sets in Redis and persist to PostgreSQL.
    """
    try:
        result = await GridPrecomputeService.precompute_and_store_puzzle(
            session=session,
            puzzle_id=puzzle_id,
            redis_client=redis_client,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Error during puzzle precomputation: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post(
    "/generate",
    summary="Dynamically generate, precompute, and publish a new 3x3 Grid puzzle",
    status_code=status.HTTP_200_OK,
)
async def generate_grid_puzzle(
    target_date: Optional[str] = None,
    puzzle_number: int = 1,
    session: AsyncSession = Depends(get_async_session),
    redis_client: Optional[Redis] = Depends(get_redis),
) -> Dict[str, Any]:
    """
    Triggers dynamic deterministic generation and precomputation for a given date (defaults to today).
    """
    from datetime import date, datetime
    t_date = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else datetime.utcnow().date()

    puzzle = await GridPrecomputeService.generate_daily_grid_puzzle(
        session=session,
        target_date=t_date,
        puzzle_number=puzzle_number,
        redis_client=redis_client,
    )

    return {
        "puzzle_id": str(puzzle.puzzle_id),
        "target_date": str(puzzle.target_date),
        "game_type": puzzle.game_type,
        "rows": puzzle.puzzle_data.get("rows"),
        "columns": puzzle.puzzle_data.get("columns"),
        "cell_cardinalities": puzzle.puzzle_data.get("cell_cardinalities"),
    }

