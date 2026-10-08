"""Memory polling and the memory page:

    GET    /messages/{message_id}/memory-updates
    GET    /users/me/memory
    DELETE /users/me/memory/{memory_id}
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.dependencies import get_current_user
from app.brain.memory_repository import MemoryRepository, get_memory_repository
from app.brain.profile_repository import ProfileRepository, get_profile_repository
from app.db.memory_event_repository import MemoryEventRepository, get_memory_event_repository
from app.db.message_repository import MessageRepository, get_message_repository
from app.db.models import UserRow
from app.models.memory import MemoryItem, MemoryPageResponse, MemoryUpdatesResponse

router = APIRouter()


@router.get("/messages/{message_id}/memory-updates", response_model=MemoryUpdatesResponse)
async def get_memory_updates(
    message_id: uuid.UUID,
    user: UserRow = Depends(get_current_user),
    messages: MessageRepository = Depends(get_message_repository),
    events: MemoryEventRepository = Depends(get_memory_event_repository),
) -> MemoryUpdatesResponse:
    """What the background memory task did with one user message. Postgres only."""
    message = await messages.get_for_user(message_id, user.id)
    # Only user messages have a memory status; anything else is "not found".
    if message is None or message.memory_status is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

    return MemoryUpdatesResponse(
        status=message.memory_status,
        updates=await events.list_for_message(message.id),
    )


@router.get("/users/me/memory", response_model=MemoryPageResponse)
async def get_memory_page(
    user: UserRow = Depends(get_current_user),
    memories: MemoryRepository = Depends(get_memory_repository),
    profiles: ProfileRepository = Depends(get_profile_repository),
) -> MemoryPageResponse:
    """Everything the assistant currently remembers about the user. Neo4j only."""
    active = await memories.get_active_all(str(user.id))
    active.sort(key=lambda memory: memory.created_at, reverse=True)

    grouped: dict[str, list[MemoryItem]] = {}
    for memory in active:
        grouped.setdefault(memory.life_area, []).append(MemoryItem(**memory.model_dump()))

    return MemoryPageResponse(
        profile=await profiles.get_profile(str(user.id)),
        memories=grouped,
    )


@router.delete("/users/me/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    user: UserRow = Depends(get_current_user),
    memories: MemoryRepository = Depends(get_memory_repository),
) -> Response:
    """Hard-delete one memory. Past memory_events rows stay as history."""
    deleted = await memories.delete(str(user.id), memory_id)
    if not deleted:
        # Also the answer for another user's memory: its existence is not revealed.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
