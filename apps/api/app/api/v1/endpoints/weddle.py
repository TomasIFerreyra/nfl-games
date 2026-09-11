from datetime import date, datetime, timezone
import json
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.schemas.weddle import (
    WeddleGuessRequest,
    WeddleGuessResponse,
    WeddlePlayer,
)
from app.services.weddle_service import WeddleService

router = APIRouter(prefix="/weddle", tags=["Guess the Player (Weddle)"])


class WeddleHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


@router.get(
    "/target/{puzzle_id}",
    response_model=WeddlePlayer,
    summary="Reveal mystery player target upon game over or surrender",
)
async def reveal_weddle_target(
    puzzle_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> WeddlePlayer:
    """
    Reveals the target player for a completed or surrendered game session.
    """
    puzzle: Optional[DailyPuzzle] = None
    try:
        uid = uuid.UUID(str(puzzle_id))
        stmt = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
        puzzle = (await session.execute(stmt)).scalar_one_or_none()
    except (ValueError, AttributeError):
        pass

    target_player: Optional[WeddlePlayer] = None

    if puzzle and puzzle.game_type == "WEDDLE":
        raw_data = puzzle.puzzle_data
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        target_id = raw_data.get("target_player_id")
        if target_id:
            target_player = WeddleService.get_player(target_id)
        if not target_player:
            target_player = WeddleService.select_daily_target(puzzle.target_date)
    else:
        # Fallback to date-based deterministic target
        target_date = datetime.now(timezone.utc).date()
        target_player = WeddleService.select_daily_target(target_date)

    if not target_player:
        raise WeddleHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target player could not be determined for this puzzle.",
            error_code="TARGET_NOT_FOUND",
        )

    return target_player


@router.post(
    "/guess",
    response_model=WeddleGuessResponse,
    summary="Submit and compare a player guess against the daily mystery target",
)
async def submit_weddle_guess(
    payload: WeddleGuessRequest,
    session: AsyncSession = Depends(get_async_session),
) -> WeddleGuessResponse:
    """
    Compares a guessed player against the daily target mystery player across 8 attributes.
    Enforces maximum of 6 guesses and reveals the target mystery player ONLY when game is over.
    """
    if not payload.player_id or not str(payload.player_id).strip():
        raise WeddleHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="player_id must not be empty.",
            error_code="INVALID_PLAYER_ID",
        )

    # 1. Resolve Target Player
    puzzle: Optional[DailyPuzzle] = None
    try:
        uid = uuid.UUID(str(payload.puzzle_id))
        stmt = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
        puzzle = (await session.execute(stmt)).scalar_one_or_none()
    except (ValueError, AttributeError):
        pass

    target_player: Optional[WeddlePlayer] = None

    if puzzle and puzzle.game_type == "WEDDLE":
        raw_data = puzzle.puzzle_data
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        target_id = raw_data.get("target_player_id")
        if target_id:
            target_player = WeddleService.get_player(target_id)
        if not target_player:
            target_player = WeddleService.select_daily_target(puzzle.target_date)
    else:
        # If demo or date identifier passed, select deterministically based on date
        target_date = datetime.now(timezone.utc).date()
        try:
            # Check if puzzle_id is formatted as a date YYYY-MM-DD
            target_date = date.fromisoformat(payload.puzzle_id)
        except (ValueError, TypeError):
            pass
        target_player = WeddleService.select_daily_target(target_date)

    if not target_player:
        raise WeddleHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target puzzle could not be resolved.",
            error_code="PUZZLE_NOT_FOUND",
        )

    # 2. Resolve Guessed Player
    guessed_player = WeddleService.get_player(payload.player_id)

    # If not found in static active pool, check database
    if not guessed_player:
        stmt_player = select(Player).where(
            (Player.player_id == payload.player_id)
            | (Player.gsis_id == payload.player_id)
            | (Player.full_name == payload.player_id)
        )
        db_player = (await session.execute(stmt_player)).scalar_one_or_none()
        if db_player:
            guessed_player = await WeddleService.resolve_from_db(db_player, session)

    if not guessed_player:
        raise WeddleHTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Player with identifier '{payload.player_id}' is not recognized.",
            error_code="UNKNOWN_PLAYER",
        )


    # 3. Evaluate Guess Comparison
    response = WeddleService.evaluate_guess(
        target=target_player,
        guessed=guessed_player,
        previous_guesses=payload.previous_guesses,
    )

    return response
