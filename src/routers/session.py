"""Session management API endpoints for Medical Billing Copilot.

Implements session CRUD operations for conversation management.

Requirements: 8.4, 8.5
"""

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


def _parse_citations(citations_json: str | None) -> list[Citation] | None:
    """Parse citations JSON string to list of Citation objects."""
    if not citations_json:
        return None
    import json
    try:
        citations_data = json.loads(citations_json)
        return [Citation(**c) for c in citations_data]
    except (json.JSONDecodeError, TypeError):
        return None


def _session_to_response(session: Session) -> SessionResponse:
    """Convert Session model to SessionResponse."""
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at.replace(tzinfo=timezone.utc)
        if session.created_at.tzinfo is None
        else session.created_at,
        updated_at=session.updated_at.replace(tzinfo=timezone.utc)
        if session.updated_at.tzinfo is None
        else session.updated_at,
        last_activity=session.last_activity.replace(tzinfo=timezone.utc)
        if session.last_activity.tzinfo is None
        else session.last_activity,
    )


def _message_to_response(msg: MessageRecord) -> Message:
    """Convert MessageRecord model to Message."""
    return Message(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        citations=_parse_citations(msg.citations_json),
        timestamp=msg.created_at.replace(tzinfo=timezone.utc)
        if msg.created_at.tzinfo is None
        else msg.created_at,
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: SessionCreate | None = None,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionResponse:
    """Create a new conversation session.
    
    POST /api/sessions - create new session
    
    Requirements: 8.4, 8.5
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    session = Session(
        id=session_id,
        user_id=current_user["user_id"],
        title=request.title if request else None,
        created_at=now,
        updated_at=now,
        last_activity=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return _session_to_response(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all sessions for the current user.
    
    GET /api/sessions - list user sessions
    
    Requirements: 8.4, 8.5
    """
    sessions = (
        db.query(Session)
        .filter(Session.user_id == current_user["user_id"])
        .order_by(Session.updated_at.desc())
        .all()
    )
    
    return [_session_to_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionWithMessages)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> SessionWithMessages:
    """Get a session with its conversation history.
    
    GET /api/sessions/{id} - get session with messages
    
    Requirements: 8.4, 8.5
    """
    session = (
        db.query(Session)
        .filter(
            Session.id == session_id,
            Session.user_id == current_user["user_id"],
        )
        .first()
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Get messages for this session
    messages = (
        db.query(MessageRecord)
        .filter(MessageRecord.session_id == session_id)
        .order_by(MessageRecord.created_at.asc())
        .all()
    )
    
    return SessionWithMessages(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at.replace(tzinfo=timezone.utc)
        if session.created_at.tzinfo is None
        else session.created_at,
        updated_at=session.updated_at.replace(tzinfo=timezone.utc)
        if session.updated_at.tzinfo is None
        else session.updated_at,
        last_activity=session.last_activity.replace(tzinfo=timezone.utc)
        if session.last_activity.tzinfo is None
        else session.last_activity,
        messages=[_message_to_response(m) for m in messages],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> None:
    """Delete a session and its messages.
    
    DELETE /api/sessions/{id} - delete session
    
    Requirements: 8.4, 8.5
    """
    session = (
        db.query(Session)
        .filter(
            Session.id == session_id,
            Session.user_id == current_user["user_id"],
        )
        .first()
    )
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Delete associated messages first
    db.query(MessageRecord).filter(MessageRecord.session_id == session_id).delete()
    
    # Delete the session
    db.delete(session)
    db.commit()
