from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.domain.top10_validator import Top10Validator
from app.schemas.top10 import Top10Entry, Top10GuessRequest, Top10GuessResponse

router = APIRouter(prefix="/top10", tags=["Top 10 Leaderboard"])


@router.get(
    "/leaderboard/{puzzle_id}",
    response_model=List[Top10Entry],
    summary="Reveal full Top 10 leaderboard (used after game over or resignation)",
)
async def get_top10_leaderboard(
    puzzle_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> List[Top10Entry]:
    puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == puzzle_id)
    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "TOP10":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Top 10 puzzle not found for the supplied puzzle_id.",
        )

    leaderboard = puzzle.puzzle_data.get("leaderboard", [])
    return [
        Top10Entry(
            rank=entry["rank"],
            player_id=entry["player_id"],
            player_name=entry["player_name"],
            metric_value=entry["metric_value"],
            formatted_value=entry["formatted_value"],
            active_years=entry.get("active_years"),
            primary_franchise=entry.get("primary_franchise"),
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
    puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == payload.puzzle_id)
    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "TOP10":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid Top 10 puzzle not found for the supplied puzzle_id.",
        )

    # Resolve guessed player display name
    player_query = select(Player.full_name).where(Player.player_id == payload.player_id)
    player_name = (await session.execute(player_query)).scalar() or payload.player_id

    is_hit, entry_dict = Top10Validator.evaluate_guess(
        puzzle_data=puzzle.puzzle_data,
        player_id=payload.player_id,
    )

    if is_hit and entry_dict:
        entry_model = Top10Entry(
            rank=entry_dict["rank"],
            player_id=entry_dict["player_id"],
            player_name=entry_dict["player_name"],
            metric_value=entry_dict["metric_value"],
            formatted_value=entry_dict["formatted_value"],
            active_years=entry_dict.get("active_years"),
            primary_franchise=entry_dict.get("primary_franchise"),
        )
        return Top10GuessResponse(
            is_hit=True,
            entry=entry_model,
            player_name=player_name,
            strikes_added=0,
        )

    # Miss / Strike
    return Top10GuessResponse(
        is_hit=False,
        entry=None,
        player_name=player_name,
        strikes_added=1,
    )
