from datetime import date, datetime
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class DailyPuzzleResponse(BaseModel):
    puzzle_id: uuid.UUID
    puzzle_number: int
    target_date: date
    game_type: str = Field(..., description="grid, reverse_grid, connections, top10")
    puzzle_data: Dict[str, Any] = Field(..., description="Game payload stripped of cheat/solution data")
    created_at: datetime
