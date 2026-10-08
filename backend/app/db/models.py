"""ORM models for the four Postgres tables. The schema itself is created by Alembic."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    # Generated here and reused as the Neo4j User.id.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)  # stored lower-cased
    password_hash: Mapped[str] = mapped_column(Text)
    # App flag only; the profile data itself lives in Neo4j.
    profile_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    # Used only when CLARIFY_ENABLED is on.
    pending_clarification: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_session_id_created_at", "session_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    # Denormalized so ownership can be checked without joining sessions.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(Text)  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)

    # Assistant messages only.
    type: Mapped[str | None] = mapped_column(Text)  # "answer" or "clarification"
    context_used: Mapped[list | None] = mapped_column(JSONB)
    used_memory_ids: Mapped[list | None] = mapped_column(JSONB)
    route_intent: Mapped[str | None] = mapped_column(Text)
    route_areas: Mapped[list | None] = mapped_column(JSONB)

    # User messages only: "pending", "done", "skipped" or "failed".
    memory_status: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryEventRow(Base):
    """Audit log of memory writes. The memory polling endpoint reads from here."""

    __tablename__ = "memory_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The user message that produced this memory write.
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text)  # "created", "updated" or "profile_corrected"
    # Neo4j memory node id; null for profile corrections.
    memory_id: Mapped[str | None] = mapped_column(Text)
    # Snapshot for display, so the event still reads correctly after the memory changes.
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    life_area: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
