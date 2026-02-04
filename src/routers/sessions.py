"""Session management API endpoints for Medical Billing Copilot.

Implements session CRUD operations.

Requirements: 8.4, 8.5
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DBSession

from src.db.config import get_db
from src.db.models import MessageRecord, Session
from src.schemas.common import Citation, Message
from src.schemas.session import SessionCreate, SessionResponse, SessionWithMessages
from src.services import AuthService, InvalidTokenError, TokenExpiredError

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: DBSession = Depends(get_db),
) -> dict:
    """Validate JWT token and return current user info."""
    auth_service = AuthService(db)
    try:
        token_payload = auth_service.validate_token(credentials.credentials)
        return {
            "user_id": token_payload.user_id,
            "email": token_payload.email,
            "role": token_payload.role,
        }
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("", response_model=SessionResponse)
async def create_session(
    request: SessionCreate = None,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionResponse:
    """Create a new conversation session."""
    now = datetime.now(timezone.utc)
    session = Session(
        id=str(uuid.uuid4()),
        user_id=current_user["user_id"],
        title=request.title if request else None,
        created_at=now,
        updated_at=now,
        last_activity=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionResponse.model_validate(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all sessions for the current user."""
    sessions = (
        db.query(Session)
        .filter(Session.user_id == current_user["user_id"])
        .order_by(Session.updated_at.desc())
        .all()
    )
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionWithMessages)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionWithMessages:
    """Get a session with its messages."""
    session = (
        db.query(Session)
        .filter(Session.id == session_id, Session.user_id == current_user["user_id"])
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Get messages for this session
    message_records = (
        db.query(MessageRecord)
        .filter(MessageRecord.session_id == session_id)
        .order_by(MessageRecord.created_at.asc())
        .all()
    )
    
    messages = []
    for record in message_records:
        citations = None
        if record.citations_json:
            try:
                citations_data = json.loads(record.citations_json)
                citations = [Citation.model_validate(c) for c in citations_data]
            except (json.JSONDecodeError, ValueError):
                pass
        
        messages.append(Message(
            id=record.id,
            role=record.role,
            content=record.content,
            citations=citations,
            timestamp=record.created_at,
        ))
    
    return SessionWithMessages(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_activity=session.last_activity,
        messages=messages,
    )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> dict:
    """Delete a session and its messages."""
    session = (
        db.query(Session)
        .filter(Session.id == session_id, Session.user_id == current_user["user_id"])
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Delete messages first
    db.query(MessageRecord).filter(MessageRecord.session_id == session_id).delete()
    
    # Delete session
    db.delete(session)
    db.commit()
    
    return {"message": "Session deleted"}
