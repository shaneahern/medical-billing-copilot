"""Session management schemas for Medical Billing Copilot."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.common import Message


class SessionCreate(BaseModel):
    """Session creation request."""

    title: Optional[str] = Field(None, max_length=200, description="Optional session title")


class SessionResponse(BaseModel):
    """Session response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Session identifier")
    user_id: str = Field(..., description="User identifier")
    title: Optional[str] = Field(None, max_length=200, description="Session title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_activity: datetime = Field(..., description="Last activity timestamp")


class SessionWithMessages(SessionResponse):
    """Session with conversation history."""

    messages: list[Message] = Field(
        default_factory=list, description="Conversation messages"
    )
