"""Postgres access for the messages table (the chat history)."""

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MessageRow


class MessageRepository:
    """All queries on the messages table. Each method is one complete transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_session(self, session_id: uuid.UUID) -> list[MessageRow]:
        """Every message in the session, oldest first."""
        result = await self.db.execute(
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(MessageRow.created_at)
        )
        return list(result.scalars())

    async def get_recent(self, session_id: uuid.UUID, limit: int) -> list[MessageRow]:
        """The last `limit` messages of the session, oldest first.

        This is the short-term context: only a small window of the history is
        ever loaded, never the whole conversation.
        """
        result = await self.db.execute(
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(MessageRow.created_at.desc())
            .limit(limit)
        )
        newest_first = list(result.scalars())
        return list(reversed(newest_first))


def get_message_repository(db: AsyncSession = Depends(get_db)) -> MessageRepository:
    """FastAPI dependency: a MessageRepository bound to this request's database session."""
    return MessageRepository(db)
