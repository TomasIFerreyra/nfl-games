import json
import uuid
from typing import List

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


@router.get(
    "/solution/{puzzle_id}",
    response_model=List[ConnectionsGroup],
    summary="Reveal all connections groups (used after game over or completion)",
)
async def get_connections_solution(
    puzzle_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> List[ConnectionsGroup]:
    try:
        uid = uuid.UUID(str(puzzle_id))
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
    except (ValueError, AttributeError):
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == str(puzzle_id))

    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "CONNECTIONS":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Connections puzzle not found for the supplied puzzle_id.",
        )

    raw_data = puzzle.puzzle_data
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    groups_data = raw_data.get("groups", [])
    return [
        ConnectionsGroup(
            group_id=g["group_id"],
            tier=g["tier"],
            title=g["title"],
            item_ids=g["item_ids"],
            explanation=g.get("explanation", ""),
        )
        for g in groups_data
    ]


@router.post(
    "/validate-group",
    response_model=ConnectionsValidateResponse,
    summary="Validate 4-item selection for Connections game",
)
async def validate_connections_group(
    payload: ConnectionsValidateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ConnectionsValidateResponse:
    try:
        uid = uuid.UUID(str(payload.puzzle_id))
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
    except (ValueError, AttributeError):
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == str(payload.puzzle_id))

    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "CONNECTIONS":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Connections puzzle not found for the supplied puzzle_id.",
        )

    raw_data = puzzle.puzzle_data
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    is_match, matched_group, is_one_away, max_count = ConnectionsValidator.validate_group(
        puzzle_data=raw_data,
        selected_item_ids=payload.selected_item_ids,
    )

    group_model = None
    if matched_group:
        group_model = ConnectionsGroup(
            group_id=matched_group["group_id"],
            tier=matched_group["tier"],
            title=matched_group["title"],
            item_ids=matched_group["item_ids"],
            explanation=matched_group.get("explanation", ""),
        )

    return ConnectionsValidateResponse(
        is_match=is_match,
        group=group_model,
        is_one_away=is_one_away,
        matched_count=max_count,
    )
