from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.profile import Profile

MemoryKind = Literal["goal", "interest", "preference", "memory"]


class MemoryNode(BaseModel):
    """One Goal / Interest / Preference / Memory node from the Shared Brain."""

    id: str
    kind: MemoryKind
    title: str
    # One clean, self-contained sentence, e.g. "Career goal: plans to switch jobs in 2027."
    text: str
    life_area: str
    attributes: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    status: Literal["active", "superseded"] = "active"
    superseded_by: str | None = None
    created_at: datetime
    updated_at: datetime
    # Postgres ids of where this memory came from.
    source_session_id: str | None = None
    source_message_id: str | None = None


class MemoryUpdate(BaseModel):
    """One memory write, as shown in the "memory updated" indicator."""

    model_config = ConfigDict(from_attributes=True)

    action: Literal["created", "updated", "profile_corrected"]
    kind: str
    title: str
    life_area: str
    memory_id: str | None


class MemoryUpdatesResponse(BaseModel):
    status: Literal["pending", "done", "skipped", "failed"]
    updates: list[MemoryUpdate]


class MemoryItem(BaseModel):
    """A memory as shown on the memory page."""

    id: str
    kind: MemoryKind
    title: str
    text: str
    life_area: str
    attributes: dict
    created_at: datetime


class MemoryPageResponse(BaseModel):
    profile: Profile | None
    # Active memories grouped by life area, e.g. {"career": [...], "health": [...]}.
    memories: dict[str, list[MemoryItem]]
