"""Context selection: one retriever per intent decides what goes into the prompt.

Each retriever fills `state.memories` and may narrow `state.profile_view` and
`state.history`. Nothing else from the Shared Brain ever reaches the LLM.
"""

import math
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.brain.memory_repository import MemoryRepository
from app.chat.state import TurnState
from app.config import Settings
from app.models.memory import MemoryNode

FALLBACK_MEMORY_COUNT = 3
SMALLTALK_HISTORY_MESSAGES = 2


def relevance_score(memory: MemoryNode, now: datetime, half_life_days: int) -> float:
    """score = confidence x importance x recency_decay"""
    days_since_updated = max((now - memory.updated_at).total_seconds() / 86400, 0)
    recency_decay = math.exp(-days_since_updated / half_life_days)
    return memory.confidence * memory.importance * recency_decay


async def retrieve_general(state: TurnState, memories: MemoryRepository, settings: Settings) -> None:
    """Profile + zodiac + the top-K active memories in the routed life areas."""
    areas = state.route.areas
    found = await memories.get_active_by_areas(state.user_id, areas) if areas else []

    if not found and areas in ([], ["general"]):
        # No specific area was detected and nothing is filed under "general":
        # fall back to the few most important memories from any area.
        everything = await memories.get_active_all(state.user_id)
        everything.sort(key=lambda memory: memory.importance, reverse=True)
        state.memories = everything[:FALLBACK_MEMORY_COUNT]
        return

    now = datetime.now(timezone.utc)
    found.sort(
        key=lambda memory: relevance_score(memory, now, settings.recency_half_life_days),
        reverse=True,
    )
    state.memories = found[: settings.top_k_memories]


async def retrieve_followup(state: TurnState, memories: MemoryRepository, settings: Settings) -> None:
    """Profile + zodiac + exactly the memories the previous assistant reply used. No new search."""
    previous_reply = next((row for row in reversed(state.history) if row.role == "assistant"), None)
    previous_ids = (previous_reply.used_memory_ids or []) if previous_reply is not None else []

    if not previous_ids:
        # Nothing to follow up on (first message, or the last reply used no memories):
        # treat it as a general question, and record it as one.
        state.route.intent = "general"
        await retrieve_general(state, memories, settings)
        return

    state.memories = await memories.get_active_by_ids(state.user_id, previous_ids)


async def retrieve_memory_query(state: TurnState, memories: MemoryRepository, settings: Settings) -> None:
    """Everything remembered in the asked-about areas (or everything), newest first."""
    specific_areas = [area for area in state.route.areas if area != "general"]
    if specific_areas:
        found = await memories.get_active_by_areas(state.user_id, specific_areas)
    else:
        found = await memories.get_active_all(state.user_id)

    found.sort(key=lambda memory: memory.created_at, reverse=True)
    state.memories = found
    # Profile facts and the sign name are remembered facts too, but no astrology flavour.
    state.profile_view = "facts"


async def retrieve_profile_query(state: TurnState, memories: MemoryRepository, settings: Settings) -> None:
    """Profile + zodiac only."""
    state.memories = []


async def retrieve_smalltalk(state: TurnState, memories: MemoryRepository, settings: Settings) -> None:
    """The user's name and the last two messages. Nothing else."""
    state.memories = []
    state.profile_view = "name"
    state.history = state.history[-SMALLTALK_HISTORY_MESSAGES:]


Retriever = Callable[[TurnState, MemoryRepository, Settings], Awaitable[None]]

RETRIEVERS: dict[str, Retriever] = {
    "general": retrieve_general,
    "followup": retrieve_followup,
    "memory_query": retrieve_memory_query,
    "profile_query": retrieve_profile_query,
    "smalltalk": retrieve_smalltalk,
}
