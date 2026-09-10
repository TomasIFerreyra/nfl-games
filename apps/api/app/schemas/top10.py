import uuid
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class Top10Entry(BaseModel):
    rank: int = Field(..., ge=1, le=10, description="Rank position (1 to 10)")
    player_id: str = Field(..., description="Canonical UUID or GSIS/PFR player ID")
    player_name: str = Field(..., description="Full player name")
    metric_value: float = Field(..., description="Raw numerical or chronological metric value")
    formatted_value: str = Field(..., description="Human-readable formatted metric (e.g. '5,477 yds' or '2023 (BAL)')")
    headshot_url: Optional[str] = Field(None, description="Official transparent headshot URL")
    active_years: Optional[str] = Field(None, description="Active career span (e.g. '2017-Present' or '1998-2015')")
    primary_franchise: Optional[str] = Field(None, description="Primary franchise abbreviation or code")
    tied_player_ids: Optional[List[str]] = Field(default=None, description="Other player IDs tied at this exact rank value")


class Top10PuzzleData(BaseModel):
    category_id: str = Field(..., description="Unique category identifier")
    title: str = Field(..., description="Category title display prompt")
    description: Optional[str] = Field(None, description="Contextual subtitle or rule clarification")
    metric_label: str = Field(..., description="Label for leaderboard units (e.g. 'Passing Yards', 'Draft Pick')")
    slots_count: int = Field(default=10, description="Total ranked slots")
    leaderboard: List[Top10Entry] = Field(..., min_length=10, max_length=10, description="Ordered top 10 entries")


class Top10GuessRequest(BaseModel):
    puzzle_id: Union[uuid.UUID, str] = Field(..., description="Target daily puzzle ID")
    player_id: str = Field(..., min_length=1, description="Player ID or name submitted by user")
    previous_guesses: Optional[List[str]] = Field(default=None, description="List of player IDs already submitted in this session")


class Top10GuessResponse(BaseModel):
    is_hit: bool = Field(..., description="True if guess matches an unrevealed slot in the top 10")
    entry: Optional[Top10Entry] = Field(None, description="Revealed leaderboard entry if is_hit is True")
    player_name: Optional[str] = Field(None, description="Resolved full name of submitted player")
    strikes_added: int = Field(default=0, ge=0, le=1, description="1 if miss, 0 if hit or duplicate")
    current_strikes: Optional[int] = Field(None, description="Updated total strikes count")
    max_strikes: int = Field(default=3, description="Maximum strike ceiling before game over")
    is_game_over: bool = Field(default=False, description="True if strikes >= 3 or all 10 slots solved")
    is_repeated: bool = Field(default=False, description="True if player was already guessed in this session")
    reason: Optional[str] = Field(None, description="Reason for validation result or rejection")
    total_found: Optional[int] = Field(None, description="Number of revealed slots so far")
    remaining_unrevealed: Optional[int] = Field(None, description="Number of remaining masked slots")
