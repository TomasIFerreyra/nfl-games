import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.player import PlayerSummary


class GridCriterion(BaseModel):
    criterion_id: str
    type: str = Field(..., description="FRANCHISE, STAT_SEASON, STAT_CAREER, ACCOLADE, DRAFT_ROUND, COLLEGE")
    display_title: str
    subtitle: Optional[str] = None
    icon_url: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class GridPuzzleData(BaseModel):
    rows: List[GridCriterion] = Field(..., min_length=3, max_length=3)
    columns: List[GridCriterion] = Field(..., min_length=3, max_length=3)
    min_cardinality_guarantee: int = Field(default=3, ge=3)


class GridValidateRequest(BaseModel):
    puzzle_id: uuid.UUID
    row_index: int = Field(..., ge=0, le=2)
    col_index: int = Field(..., ge=0, le=2)
    player_id: str


class GridValidateResponse(BaseModel):
    is_valid: bool
    row_index: int
    col_index: int
    player: Optional[PlayerSummary] = None
    rarity_score: Optional[float] = Field(None, description="Smoothed Bayesian rarity percentage (0.01 - 100.0%)")
    total_picks_for_cell: Optional[int] = None
    player_picks_for_cell: Optional[int] = None
    possible_answers_count: Optional[int] = None
    failed_criteria: Optional[List[str]] = None
    reason: Optional[str] = None
