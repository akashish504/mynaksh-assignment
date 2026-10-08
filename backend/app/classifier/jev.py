"""Primary classifier: TypeSafe AI's Jev model, one `system_one` call per message."""

from langsmith import traceable
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy

from app.classifier.base import (
    AREA_DESCRIPTIONS,
    CONTEXT_MESSAGES,
    INTENT_DESCRIPTIONS,
    RouteResult,
)
from app.db.models import MessageRow

DURABLE_FACT_STATEMENT = (
    "The new user message states a lasting personal fact, goal, preference, "
    "or life event worth remembering."
)


class JevClassifier:
    def __init__(self, api_key: str, model: str, timeout_seconds: float, area_threshold: float):
        # The SDK ships an async client, so no thread is needed.
        # Retries are off: on any failure we move straight to the LLM classifier
        # instead of making the user wait.
        self.client = AsyncTypeSafeClient(
            api_key=api_key,
            model=model,  # pinned version, never "jev-latest"
            timeout=timeout_seconds,
            retry=RetryPolicy(max_retries=0),
        )
        self.area_threshold = area_threshold

    @traceable(name="classifier.jev")
    async def route(self, history: list[MessageRow], message: str) -> RouteResult:
        state = {
            "recent_messages": [
                {"role": row.role, "content": row.content} for row in history[-CONTEXT_MESSAGES:]
            ],
            "new_user_message": message,
        }

        # Choice: pick one of the 5 intents. Noul: a yes/no probability.
        questions = {
            "intent": Choice(
                instructions="What kind of message is the new user message?",
                criteria=INTENT_DESCRIPTIONS,
            ),
            "has_durable_fact": Noul(instructions=DURABLE_FACT_STATEMENT),
        }
        for area, description in AREA_DESCRIPTIONS.items():
            questions[f"area_{area}"] = Noul(
                instructions=f"The new user message is about {description}."
            )

        result = await self.client.system_one(state=state, questions=questions)

        areas = [
            area
            for area in AREA_DESCRIPTIONS
            if result.nouls[f"area_{area}"].noul >= self.area_threshold
        ]
        return RouteResult(
            intent=result.choices["intent"].choice,
            intent_confidence=result.choices["intent"].confidence,
            areas=areas or ["general"],
            has_durable_fact=result.nouls["has_durable_fact"].noul,
            source="jev",
        )
