from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InvalidParam(BaseModel):
    name: str = Field(..., description="Field or parameter name that failed validation")
    reason: str = Field(..., description="Description of why the value is invalid")


class ProblemDetail(BaseModel):
    """RFC 7807 Compliant Problem Details representation for all API errors."""
    type: str = Field(..., description="URI reference identifying the error type")
    title: str = Field(..., description="Short human-readable summary of the problem type")
    status: int = Field(..., description="HTTP status code")
    detail: str = Field(..., description="Human-readable explanation specific to this occurrence")
    instance: str = Field(..., description="URI reference identifying the specific occurrence of the problem")
    error_code: str = Field(..., description="Machine-readable application error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of error occurrence")
    invalid_params: Optional[List[InvalidParam]] = Field(
        default=None, description="Detailed breakdown of invalid parameters"
    )
