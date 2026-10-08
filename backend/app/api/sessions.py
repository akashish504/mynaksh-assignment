"""Chat windows: POST /sessions, GET /sessions, GET /sessions/{id}/messages."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.db.message_repository import MessageRepository, get_message_repository
from app.db.models import UserRow
from app.db.session_repository import SessionRepository, get_session_repository
from app.models.session import MessageResponse, SessionResponse

router = APIRouter(prefix="/sessions")


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    user: UserRow = Depends(get_current_user),
    sessions: SessionRepository = Depends(get_session_repository),
) -> SessionResponse:
    return await sessions.create(user.id)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    user: UserRow = Depends(get_current_user),
    sessions: SessionRepository = Depends(get_session_repository),
) -> list[SessionResponse]:
    return await sessions.list_for_user(user.id)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session_id: uuid.UUID,
    user: UserRow = Depends(get_current_user),
    sessions: SessionRepository = Depends(get_session_repository),
    messages: MessageRepository = Depends(get_message_repository),
) -> list[MessageResponse]:
    session = await sessions.get_for_user(session_id, user.id)
    if session is None:
        # 404 for both "does not exist" and "belongs to someone else", so a
        # session id never reveals whether another user's session exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    return await messages.list_for_session(session.id)
