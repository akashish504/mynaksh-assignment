"""Postgres access for memory_events (the audit log) and a message's memory_status."""

import uuid

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MemoryEventRow, MessageRow


class MemoryEventRepository:
    """Each method is one complete transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_done(self, message_id: uuid.UUID, events: list[MemoryEventRow]) -> None:
        """Store the events and mark the message 'done', together in one transaction."""
        self.db.add_all(events)
        await self.db.execute(
            update(MessageRow).where(MessageRow.id == message_id).values(memory_status="done")
        )
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def set_status(self, message_id: uuid.UUID, status: str) -> None:
        await self.db.execute(
            update(MessageRow).where(MessageRow.id == message_id).values(memory_status=status)
        )
        await self.db.commit()

    async def list_for_message(self, message_id: uuid.UUID) -> list[MemoryEventRow]:
        result = await self.db.execute(
            select(MemoryEventRow)
            .where(MemoryEventRow.message_id == message_id)
            .order_by(MemoryEventRow.created_at)
        )
        return list(result.scalars())


def get_memory_event_repository(db: AsyncSession = Depends(get_db)) -> MemoryEventRepository:
    """FastAPI dependency: a MemoryEventRepository bound to this request's database session."""
    return MemoryEventRepository(db)
