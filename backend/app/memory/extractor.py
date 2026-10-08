"""Extraction: one LLM call that decides what in a user message is worth remembering."""

from datetime import date

from langsmith import traceable

from app.brain.schema import LIFE_AREAS
from app.llm.base import LLMProvider
from app.memory.schemas import ExtractedItem, ExtractionOutput
from app.models.memory import MemoryNode
from app.models.profile import Profile


def build_system_prompt(today: date) -> str:
    return f"""You maintain the long-term memory of an astrology assistant. Read the NEW USER MESSAGE and decide what, if anything, is worth remembering about the user for future conversations.

Today's date is {today.isoformat()} (UTC). Use it to turn relative times into absolute ones: "next year" is {today.year + 1}.

Reply with JSON: {{"items": [...]}}. Use an empty list when nothing is worth storing.

STORE: stable facts, goals, preferences, interests, significant life events.
DO NOT STORE: greetings, questions, passing moods, the assistant's own statements or predictions.

Each item has these fields:
- action: "create" for something new. "update" when the user changes or corrects one of the EXISTING MEMORIES; put that memory's id in target_id. "skip" when it is already stored with the same meaning.
- target_id: the id of the existing memory for "update", otherwise null.
- kind: "goal", "interest", "preference", "memory" (a fact or a significant life event), or "profile_correction" (the user states or corrects their own name, date of birth, birth time or birth place).
- title: a few words.
- text: one clean, self-contained sentence, for example "Career goal: plans to switch jobs in {today.year + 1}."
- life_area: exactly one of: {", ".join(LIFE_AREAS)}.
- attributes: name/value details such as target_year or timeframe. Use an empty list if there are none.
- profile_field: for a profile_correction, one of name, dob, birth_time, birth_place. Otherwise null.
- profile_value: for a profile_correction, the new value: dob as YYYY-MM-DD, birth_time as HH:MM (24-hour), name and birth_place as plain text. Otherwise null. Do not emit a profile_correction for a value the CURRENT PROFILE already has.
- confidence: 0 to 1, how clearly the user stated it.
- importance: 0 to 1, how much it matters for future guidance."""


def build_user_prompt(
    message: str,
    recent_messages: list[dict],
    existing_memories: list[MemoryNode],
    profile: Profile | None,
) -> str:
    if profile is None:
        profile_text = "(nothing yet)"
    else:
        birth_time = profile.birth_time.strftime("%H:%M") if profile.birth_time else "unknown"
        profile_text = (
            f"name: {profile.name or 'unknown'}\n"
            f"dob: {profile.dob.isoformat() if profile.dob else 'unknown'}\n"
            f"birth_time: {birth_time}\n"
            f"birth_place: {profile.birth_place or 'unknown'}"
        )

    memories_text = "\n".join(
        f"{memory.id} | {memory.kind} | {memory.life_area} | {memory.text}"
        for memory in existing_memories
    )
    recent_text = "\n".join(f"{item['role']}: {item['content']}" for item in recent_messages)

    return (
        f"CURRENT PROFILE:\n{profile_text}\n\n"
        f"EXISTING MEMORIES (id | kind | life_area | text):\n{memories_text or '(none)'}\n\n"
        f"RECENT MESSAGES:\n{recent_text or '(none)'}\n\n"
        f"NEW USER MESSAGE:\n{message}"
    )


class MemoryExtractor:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    @traceable(name="memory.extract")
    async def extract(
        self,
        message: str,
        recent_messages: list[dict],
        existing_memories: list[MemoryNode],
        profile: Profile | None,
        today: date,
    ) -> list[ExtractedItem]:
        messages = [
            {"role": "system", "content": build_system_prompt(today)},
            {
                "role": "user",
                "content": build_user_prompt(message, recent_messages, existing_memories, profile),
            },
        ]
        output = await self.llm.generate_json(messages, ExtractionOutput)
        return output.items
