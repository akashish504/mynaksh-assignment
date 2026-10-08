import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SessionResponse(BaseModel):
    # from_attributes lets FastAPI build this straight from a SessionRow.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    # Assistant messages only.
    type: Literal["answer", "clarification"] | None
    context_used: list[str] | None
    # User messages only.
    memory_status: Literal["pending", "done", "skipped", "failed"] | None
