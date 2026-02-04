"""Query processing schemas for Medical Billing Copilot."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from src.schemas.common import DataSource, Message, QueryType


class QueryRequest(BaseModel):
    """Query request payload."""

    session_id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="User identifier")
    query: str = Field(
        ..., min_length=1, max_length=10000, description="User query text"
    )
    context: Optional[dict[str, Any]] = Field(None, description="Additional context")


class QueryResponse(BaseModel):
    """Query response payload."""

    message: Message = Field(..., description="Response message")
    query_type: QueryType = Field(..., description="Classified query type")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Response confidence score"
    )
    data_source: DataSource = Field(..., description="Data source used")
