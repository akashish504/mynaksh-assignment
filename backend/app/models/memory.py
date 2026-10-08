from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
