import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class Top10Entry(BaseModel):
    rank: int = Field(..., ge=1, le=10)
    player_id: str
    player_name: str
    metric_value: float
    formatted_value: str
    active_years: Optional[str] = None
    primary_franchise: Optional[str] = None


class Top10PuzzleData(BaseModel):
    category_id: str
    title: str
    description: Optional[str] = None
    metric_label: str
    leaderboard: List[Top10Entry] = Field(..., min_length=10, max_length=10)


class Top10GuessRequest(BaseModel):
    puzzle_id: uuid.UUID
    player_id: str


class Top10GuessResponse(BaseModel):
    is_hit: bool
    entry: Optional[Top10Entry] = None
    player_name: Optional[str] = None
    strikes_added: int = Field(default=0, ge=0, le=1)
    current_strikes: Optional[int] = None
    max_strikes: int = 3
    is_game_over: bool = False
    total_found: Optional[int] = None
    remaining_unrevealed: Optional[int] = None
