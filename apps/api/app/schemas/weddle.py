from datetime import date
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class WeddlePlayer(BaseModel):
    """
    Rich profile of an active NFL player used for daily target selection and comparison.
    """
    player_id: str = Field(..., description="Canonical player ID or GSIS ID")
    full_name: str = Field(..., description="Player display name (e.g. 'Patrick Mahomes')")
    headshot_url: Optional[str] = Field(default=None, description="Headshot image URL")
    team: str = Field(..., description="Franchise abbreviation (e.g. 'KC', 'BUF')")
    side_of_ball: str = Field(..., description="'Offense' or 'Defense'")
    position: str = Field(..., description="Position code (e.g. 'QB', 'WR', 'CB')")
    conference: str = Field(..., description="'AFC' or 'NFC'")
    division: str = Field(..., description="'East', 'North', 'South', 'West'")
    birth_date: Optional[date] = Field(default=None, description="Canonical date of birth (YYYY-MM-DD)")
    age: int = Field(..., description="Dynamically computed age in years")
    height_inches: int = Field(..., description="Height in inches (e.g. 74)")
    height_formatted: str = Field(..., description="Height formatted as feet and inches (e.g. 6'2\")")
    jersey_number: int = Field(..., description="Jersey number (e.g. 15)")


class AttributeComparison(BaseModel):
    """
    Comparison result for a single player attribute.
    """
    status: Literal["green", "yellow", "gray"] = Field(
        ...,
        description="'green' (exact), 'yellow' (close/partial), or 'gray' (incorrect)"
    )
    direction: Optional[Literal["higher", "lower"]] = Field(
        default=None,
        description="'higher' if target > guess, 'lower' if target < guess, null if exact or non-numeric"
    )


class WeddleComparisonAttributes(BaseModel):
    """
    Comparison outcomes across all 8 comparison dimensions.
    """
    team: AttributeComparison
    side_of_ball: AttributeComparison
    position: AttributeComparison
    conference: AttributeComparison
    division: AttributeComparison
    age: AttributeComparison
    height: AttributeComparison
    jersey_number: AttributeComparison


class WeddleGuessComparison(BaseModel):
    """
    Full comparison record of the guessed player vs the target player.
    """
    player: WeddlePlayer
    attributes: WeddleComparisonAttributes


class WeddleGuessRequest(BaseModel):
    """
    Submission payload for submitting a player guess.
    """
    puzzle_id: str = Field(..., description="Puzzle UUID or date identifier")
    player_id: str = Field(..., description="Guessed player ID or GSIS ID")
    previous_guesses: Optional[List[str]] = Field(
        default_factory=list,
        description="List of player IDs already guessed in this session"
    )


class WeddleGuessResponse(BaseModel):
    """
    Response returned by POST /api/v1/weddle/guess.
    """
    is_correct: bool = Field(..., description="True if guessed player matches mystery target")
    guesses_remaining: int = Field(..., description="Remaining attempts out of 6")
    is_game_over: bool = Field(..., description="True if won or guesses exhausted")
    comparison: WeddleGuessComparison = Field(..., description="Comparison details for this guess")
    revealed_target: Optional[WeddlePlayer] = Field(
        default=None,
        description="Target mystery player revealed ONLY when is_game_over is True"
    )
