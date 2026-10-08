import uuid
from typing import Literal

from pydantic import BaseModel, field_validator

MAX_MESSAGE_LENGTH = 2000


class ChatRequest(BaseModel):
    # A `user_id` sent in the body is ignored: the user always comes from the token.
    session_id: uuid.UUID
    message: str

    @field_validator("message")
    @classmethod
    def message_has_content(cls, message: str) -> str:
        message = message.strip()
        if not message:
            raise ValueError("Message cannot be empty.")
        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message cannot be longer than {MAX_MESSAGE_LENGTH} characters.")
        return message


class ChatResponse(BaseModel):
    response: str
    user_id: uuid.UUID
    session_id: uuid.UUID
    # The id of the USER message, used to poll for memory updates.
    message_id: uuid.UUID
    type: Literal["answer", "clarification"]
    options: list[str] | None = None
    context_used: list[str]
