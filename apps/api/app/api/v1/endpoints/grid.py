from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.player import Player
from app.db.models.puzzle import DailyPuzzle
from app.db.session import get_async_session
from app.domain.grid_validator import GridValidator
from app.schemas.grid import GridValidateRequest, GridValidateResponse
from app.schemas.player import PlayerSummary

router = APIRouter(prefix="/grid", tags=["3x3 Grid"])


@router.post(
    "/validate",
    response_model=GridValidateResponse,
    summary="Validate 3x3 Grid cell guess and compute Bayesian rarity",
)
async def validate_grid_guess(
    payload: GridValidateRequest,
    session: AsyncSession = Depends(get_async_session),
) -> GridValidateResponse:
    # 1. Fetch Puzzle
    puzzle_query = select(DailyPuzzle).where(DailyPuzzle.puzzle_id == payload.puzzle_id)
    puzzle = (await session.execute(puzzle_query)).scalar_one_or_none()

    if not puzzle or puzzle.game_type != "GRID":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Valid 3x3 Grid puzzle not found for the supplied puzzle_id.",
        )

    # 2. Fetch Player
    player_query = select(Player).where(Player.player_id == payload.player_id)
    player = (await session.execute(player_query)).scalar_one_or_none()

    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player '{payload.player_id}' not found in canonical directory.",
        )

    player_summary = PlayerSummary(
        player_id=player.player_id,
        full_name=player.full_name,
        position=player.primary_position,
        headshot_url=player.headshot_url,
    )

    # 3. Retrieve row & col criteria
    puzzle_data: Dict[str, Any] = puzzle.puzzle_data
    rows: List[Dict[str, Any]] = puzzle_data.get("rows", [])
    columns: List[Dict[str, Any]] = puzzle_data.get("columns", [])

    if payload.row_index >= len(rows) or payload.col_index >= len(columns):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coordinates (row_index, col_index) are out of bounds.",
        )

    row_criterion = rows[payload.row_index]
    col_criterion = columns[payload.col_index]

    # 4. Evaluate Row Criterion
    row_satisfied, row_reason = await GridValidator.evaluate_criterion(
        session, player.player_id, row_criterion
    )

    # 5. Evaluate Column Criterion
    col_satisfied, col_reason = await GridValidator.evaluate_criterion(
        session, player.player_id, col_criterion
    )

    failed_criteria: List[str] = []
    reasons: List[str] = []

    if not row_satisfied:
        failed_criteria.append(row_criterion.get("criterion_id", "ROW"))
        if row_reason:
            reasons.append(row_reason)

    if not col_satisfied:
        failed_criteria.append(col_criterion.get("criterion_id", "COL"))
        if col_reason:
            reasons.append(col_reason)

    is_valid = (row_satisfied and col_satisfied)

    if not is_valid:
        return GridValidateResponse(
            is_valid=False,
            row_index=payload.row_index,
            col_index=payload.col_index,
            player=player_summary,
            failed_criteria=failed_criteria,
            reason="; ".join(reasons),
        )

    # 6. If Valid: Calculate smoothed Bayesian rarity & record answer
    cell_id = f"r{payload.row_index}_c{payload.col_index}"
    possible_count = puzzle_data.get("cell_cardinalities", [[10]*3]*3)[payload.row_index][payload.col_index]

    rarity_score, total_picks, player_picks = await GridValidator.compute_bayesian_rarity(
        session=session,
        puzzle_id=str(puzzle.puzzle_id),
        cell_identifier=cell_id,
        player_id=player.player_id,
        possible_answers_count=possible_count,
    )

    await GridValidator.record_answer_selection(
        session=session,
        puzzle_id=str(puzzle.puzzle_id),
        cell_identifier=cell_id,
        player_id=player.player_id,
    )

    return GridValidateResponse(
        is_valid=True,
        row_index=payload.row_index,
        col_index=payload.col_index,
        player=player_summary,
        rarity_score=rarity_score,
        total_picks_for_cell=total_picks,
        player_picks_for_cell=player_picks,
        possible_answers_count=possible_count,
    )
