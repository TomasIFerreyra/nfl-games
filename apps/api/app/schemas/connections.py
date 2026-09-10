import uuid
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class ConnectionsItem(BaseModel):
    item_id: str
    display_text: str
    subtext: Optional[str] = None


class ConnectionsGroup(BaseModel):
    group_id: str
    tier: int = Field(..., ge=1, le=4, description="1=Bronze, 2=Silver, 3=Gold, 4=Lombardi Platinum / Obsidian")
    title: str
    item_ids: List[str] = Field(..., min_length=4, max_length=4)
    explanation: str


class ConnectionsPuzzleData(BaseModel):
    items: List[ConnectionsItem] = Field(..., min_length=16, max_length=16)
    groups: List[ConnectionsGroup] = Field(..., min_length=4, max_length=4)


class ConnectionsValidateRequest(BaseModel):
    puzzle_id: Union[uuid.UUID, str]
    selected_item_ids: List[str] = Field(..., min_length=4, max_length=4)


class ConnectionsValidateResponse(BaseModel):
    is_match: bool
    group: Optional[ConnectionsGroup] = None
    is_one_away: bool = False
    matched_count: Optional[int] = None
