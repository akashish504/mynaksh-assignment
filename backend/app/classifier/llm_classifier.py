"""Second classifier: the same routing decision, asked of the general LLM as JSON."""

from langsmith import traceable
from pydantic import BaseModel, Field

from app.brain.schema import LIFE_AREAS
from app.classifier.base import (
    AREA_DESCRIPTIONS,
    CONTEXT_MESSAGES,
    INTENT_DESCRIPTIONS,
    Intent,
    RouteResult,
)
from app.db.models import MessageRow
from app.llm.base import LLMProvider


class RouteJSON(BaseModel):
    """The JSON shape the LLM must return."""

    intent: Intent
    intent_confidence: float = Field(ge=0, le=1)
    areas: list[str]
    has_durable_fact: float = Field(ge=0, le=1)


def build_system_prompt() -> str:
    intents = "\n".join(f"- {name}: {text}" for name, text in INTENT_DESCRIPTIONS.items())
    areas = "\n".join(f"- {name}: {text}" for name, text in AREA_DESCRIPTIONS.items())
    return (
        "You classify the NEW user message in a chat with an astrology assistant. "
        "Reply with JSON only.\n\n"
        "intent: exactly one of:\n"
        f"{intents}\n\n"
        "intent_confidence: your confidence in the intent, from 0 to 1.\n\n"
        "areas: every life area the new message is about, chosen only from this list. "
        "Use an empty list if none applies.\n"
        f"{areas}\n\n"
        "has_durable_fact: from 0 to 1, how likely it is that the new message states a lasting "
        "personal fact, goal, preference, or life event worth remembering. Questions, greetings "
        "and passing moods score low."
    )


class LLMClassifier:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    @traceable(name="classifier.llm")
    async def route(self, history: list[MessageRow], message: str) -> RouteResult:
        recent = "\n".join(f"{row.role}: {row.content}" for row in history[-CONTEXT_MESSAGES:])
        messages = [
            {"role": "system", "content": build_system_prompt()},
            {
                "role": "user",
                "content": f"Recent messages:\n{recent or '(none)'}\n\nNEW user message:\n{message}",
            },
        ]
        answer = await self.llm.generate_json(messages, RouteJSON)

        # The LLM must never invent a life area: anything outside the fixed list is dropped.
        areas = [area for area in answer.areas if area in LIFE_AREAS and area != "general"]
        return RouteResult(
            intent=answer.intent,
            intent_confidence=answer.intent_confidence,
            areas=areas or ["general"],
            has_durable_fact=answer.has_durable_fact,
            source="llm",
        )
