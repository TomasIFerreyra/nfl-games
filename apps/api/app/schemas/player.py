from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field


class PlayerSummary(BaseModel):
    player_id: str
    full_name: str
    position: str
    headshot_url: Optional[str] = None


class SearchIndexResponse(BaseModel):
    """
    Compact Row-Oriented Wire Protocol schema.
    Payload size optimized to ~320 KB gzipped for all 24,000+ historical players.
    Format: [id, full_name, primary_position, rookie_year, final_year, is_active]
    """
    version: str = Field(..., description="Index snapshot version string")
    fields: List[str] = Field(
        default=["id", "name", "pos", "start", "end", "active"],
        description="Field names corresponding to each row index"
    )
    players: List[List[Union[str, int, None]]] = Field(
        ...,
        description="Array-of-arrays compact player directory"
    )
