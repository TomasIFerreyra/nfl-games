from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.domain.connections_validator import ConnectionsValidator
from app.schemas.connections import (
    ConnectionsGroup,
    ConnectionsValidateRequest,
    ConnectionsValidateResponse,
)

router = APIRouter(prefix="/connections", tags=["Connections 4x4"])


@router.post(
    "/validate-group",
    response_model=ConnectionsValidateResponse,
    summary="Validate 4-item selection for Connections game",
)
async def validate_connections_group(
    payload: ConnectionsValidateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ConnectionsValidateResponse:
    puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == payload.puzzle_id)
    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "CONNECTIONS":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Connections puzzle not found for the supplied puzzle_id.",
        )

    is_match, matched_group, is_one_away, max_count = ConnectionsValidator.validate_group(
        puzzle_data=puzzle.puzzle_data,
        selected_item_ids=payload.selected_item_ids,
    )

    group_model = None
    if matched_group:
        group_model = ConnectionsGroup(
            group_id=matched_group["group_id"],
            tier=matched_group["tier"],
            title=matched_group["title"],
            item_ids=matched_group["item_ids"],
            explanation=matched_group["explanation"],
        )

    return ConnectionsValidateResponse(
        is_match=is_match,
        group=group_model,
        is_one_away=is_one_away,
        matched_count=max_count,
    )
