import json
import uuid
from typing import List, Optional

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


class ConnectionsHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


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
        raise ConnectionsHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Connections puzzle not found for the supplied puzzle_id.",
            error_code="PUZZLE_NOT_FOUND",
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
    # 1. Enforce exactly 4 items
    if len(payload.selected_item_ids) != 4:
        raise ConnectionsHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A guess must contain exactly 4 items. Received {len(payload.selected_item_ids)}.",
            error_code="INVALID_ITEM_COUNT",
        )

    # 2. Enforce duplicate rejection
    if len(set(payload.selected_item_ids)) != 4:
        raise ConnectionsHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duplicate item IDs submitted in selection. All 4 items must be distinct.",
            error_code="DUPLICATE_ITEMS_SUBMITTED",
        )

    # 3. Fetch puzzle from database
    try:
        uid = uuid.UUID(str(payload.puzzle_id))
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
    except (ValueError, AttributeError):
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == str(payload.puzzle_id))

    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "CONNECTIONS":
        raise ConnectionsHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Connections puzzle not found for the supplied puzzle_id.",
            error_code="PUZZLE_NOT_FOUND",
        )

    raw_data = puzzle.puzzle_data
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    # 4. Verify that submitted item IDs exist on the board
    board_items = raw_data.get("items", [])
    valid_board_ids = set()
    for item in board_items:
        if isinstance(item, dict):
            if "item_id" in item:
                valid_board_ids.add(str(item["item_id"]))
            if "display_text" in item:
                valid_board_ids.add(str(item["display_text"]))
                valid_board_ids.add(str(item["display_text"]).lower().strip())

    invalid_items = [
        item_id for item_id in payload.selected_item_ids
        if str(item_id) not in valid_board_ids and str(item_id).lower().strip() not in valid_board_ids
    ]
    if invalid_items:
        raise ConnectionsHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Items {invalid_items} are not present on the active puzzle board.",
            error_code="INVALID_ITEM_ID",
        )

    # 5. Evaluate match and one-away state
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
