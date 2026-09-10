import json
from typing import List
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.domain.top10_validator import Top10Validator
from app.schemas.top10 import Top10Entry, Top10GuessRequest, Top10GuessResponse

router = APIRouter(prefix="/top10", tags=["Top 10 Leaderboard"])


class Top10HTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: str):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


@router.get(
    "/leaderboard/{puzzle_id}",
    response_model=List[Top10Entry],
    summary="Reveal full Top 10 leaderboard (used after game over or resignation)",
)
async def get_top10_leaderboard(
    puzzle_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> List[Top10Entry]:
    try:
        uid = uuid.UUID(str(puzzle_id))
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
    except (ValueError, AttributeError):
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == str(puzzle_id))

    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "TOP10":
        raise Top10HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Top 10 puzzle not found for the supplied puzzle_id.",
            error_code="PUZZLE_NOT_FOUND",
        )

    raw_data = puzzle.puzzle_data
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    leaderboard = raw_data.get("leaderboard", [])
    return [
        Top10Entry(
            rank=entry["rank"],
            player_id=entry["player_id"],
            player_name=entry["player_name"],
            metric_value=entry["metric_value"],
            formatted_value=entry["formatted_value"],
            headshot_url=entry.get("headshot_url"),
            active_years=entry.get("active_years"),
            primary_franchise=entry.get("primary_franchise"),
            tied_player_ids=entry.get("tied_player_ids"),
        )
        for entry in leaderboard
    ]


@router.post(
    "/guess",
    response_model=Top10GuessResponse,
    summary="Evaluate player guess against Top 10 Leaderboard",
)
async def submit_top10_guess(
    payload: Top10GuessRequest,
    session: AsyncSession = Depends(get_async_session),
) -> Top10GuessResponse:
    if not payload.player_id or not str(payload.player_id).strip():
        raise Top10HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="player_id must not be empty.",
            error_code="INVALID_PLAYER_ID",
        )

    try:
        uid = uuid.UUID(str(payload.puzzle_id))
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == uid)
    except (ValueError, AttributeError):
        puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == str(payload.puzzle_id))

    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "TOP10":
        raise Top10HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Top 10 puzzle not found for the supplied puzzle_id.",
            error_code="PUZZLE_NOT_FOUND",
        )

    raw_data = puzzle.puzzle_data
    if isinstance(raw_data, str):
        raw_data = json.loads(raw_data)

    # Resolve player name if possible
    player_query = select(Player.full_name).where(
        (Player.player_id == payload.player_id) | (Player.gsis_id == payload.player_id)
    )
    player_name = (await session.execute(player_query)).scalar() or payload.player_id

    is_hit, entry_dict, is_repeated, strikes_added, reason = Top10Validator.evaluate_guess(
        puzzle_data=raw_data,
        player_id=payload.player_id,
        previous_guesses=payload.previous_guesses,
        guessed_player_name=player_name,
    )

    if is_repeated:
        return Top10GuessResponse(
            is_hit=False,
            entry=None,
            player_name=player_name,
            strikes_added=0,
            is_repeated=True,
            reason=reason,
        )

    if is_hit and entry_dict:
        entry_model = Top10Entry(
            rank=entry_dict["rank"],
            player_id=entry_dict["player_id"],
            player_name=entry_dict["player_name"],
            metric_value=entry_dict["metric_value"],
            formatted_value=entry_dict["formatted_value"],
            headshot_url=entry_dict.get("headshot_url"),
            active_years=entry_dict.get("active_years"),
            primary_franchise=entry_dict.get("primary_franchise"),
            tied_player_ids=entry_dict.get("tied_player_ids"),
        )
        return Top10GuessResponse(
            is_hit=True,
            entry=entry_model,
            player_name=player_name,
            strikes_added=0,
            reason=None,
        )

    # Miss / Strike
    return Top10GuessResponse(
        is_hit=False,
        entry=None,
        player_name=player_name,
        strikes_added=1,
        reason=reason,
    )
