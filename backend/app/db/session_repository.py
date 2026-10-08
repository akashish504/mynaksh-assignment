"""Postgres access for the sessions table (one session = one chat window)."""

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import SessionRow

DEFAULT_TITLE = "New chat"


class SessionRepository:
    """All queries on the sessions table. Each method is one complete transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: uuid.UUID) -> SessionRow:
        session = SessionRow(user_id=user_id, title=DEFAULT_TITLE)
        self.db.add(session)
        await self.db.commit()
        # Load the timestamps that Postgres filled in.
        await self.db.refresh(session)
        return session

    async def list_for_user(self, user_id: uuid.UUID) -> list[SessionRow]:
        """The user's sessions, most recently active first."""
        result = await self.db.execute(
            select(SessionRow)
            .where(SessionRow.user_id == user_id)
            .order_by(SessionRow.updated_at.desc(), SessionRow.created_at.desc())
        )
        return list(result.scalars())

    async def get_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionRow | None:
        """Return the session only if it belongs to this user.

        Filtering on user_id in the query itself means another user's session
        looks exactly like one that does not exist.
        """
        result = await self.db.execute(
            select(SessionRow).where(SessionRow.id == session_id, SessionRow.user_id == user_id)
        )
        return result.scalar_one_or_none()


def get_session_repository(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    """FastAPI dependency: a SessionRepository bound to this request's database session."""
    return SessionRepository(db)
