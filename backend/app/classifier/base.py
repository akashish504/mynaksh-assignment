"""The classifier (router) interface and the result every classifier returns."""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.db.models import MessageRow

Intent = Literal["general", "followup", "memory_query", "profile_query", "smalltalk"]

# One line per intent. The same wording is given to Jev and to the LLM classifier.
INTENT_DESCRIPTIONS: dict[str, str] = {
    "general": (
        "A question or request for guidance about the user's life, or a statement "
        "sharing something about their life."
    ),
    "followup": (
        "A short follow-up that only makes sense together with the previous assistant "
        "reply, such as 'why do you say that?' or 'tell me more'."
    ),
    "memory_query": "Asks what the assistant remembers or knows about the user.",
    "profile_query": "Asks about the user's own profile: their name, birth details or zodiac sign.",
    "smalltalk": "A greeting, thanks or casual chat with no real question.",
}

# What each life area covers. "general" has no description: it is what remains
# when no other area applies.
AREA_DESCRIPTIONS: dict[str, str] = {
    "career": "career, job or work",
    "finance": "money, income, savings or investments",
    "relationships": "love, dating, marriage or friendships",
    "family": "parents, children, siblings or home life",
    "health": "physical or mental health, fitness or wellbeing",
    "education": "studies, exams, courses or learning",
    "spirituality": "spirituality, faith, meditation or inner growth",
    "travel": "travel, trips or relocation",
}

# How many earlier messages a classifier sees next to the new one.
CONTEXT_MESSAGES = 3


@dataclass
class RouteResult:
    intent: Intent
    intent_confidence: float
    areas: list[str]  # subset of the 9 life areas
    has_durable_fact: float  # 0-1, the memory gate score
    source: Literal["jev", "llm", "rules"]


class Classifier(Protocol):
    async def route(self, history: list[MessageRow], message: str) -> RouteResult: ...
