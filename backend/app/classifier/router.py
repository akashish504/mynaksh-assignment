"""The fallback chain: Jev -> LLM classifier -> rules."""

import logging

from fastapi import Request
from langsmith import traceable

from app.classifier.base import Classifier, RouteResult
from app.classifier.jev import JevClassifier
from app.classifier.llm_classifier import LLMClassifier
from app.classifier.rules import RulesClassifier
from app.config import Settings
from app.db.models import MessageRow
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class FallbackClassifier:
    """Tries each classifier in turn until one gives a usable answer.

    1. Jev (skipped when CLASSIFIER=llm). Used if it answers with enough confidence.
    2. The LLM classifier, when Jev failed, timed out or was not confident.
    3. Keyword rules, when the LLM failed too.
    """

    def __init__(
        self,
        primary: Classifier | None,
        llm_classifier: Classifier,
        rules: Classifier,
        min_confidence: float,
    ):
        self.primary = primary
        self.llm_classifier = llm_classifier
        self.rules = rules
        self.min_confidence = min_confidence

    @traceable(name="classifier.route")
    async def route(self, history: list[MessageRow], message: str) -> RouteResult:
        if self.primary is not None:
            try:
                result = await self.primary.route(history, message)
                if result.intent_confidence >= self.min_confidence:
                    return result
                logger.info(
                    "Jev confidence %.2f is below %.2f; asking the LLM classifier",
                    result.intent_confidence,
                    self.min_confidence,
                )
            except Exception as error:
                logger.warning("Jev classifier failed (%r); asking the LLM classifier", error)

        try:
            # The LLM's answer replaces the whole result, not only the intent.
            return await self.llm_classifier.route(history, message)
        except Exception as error:
            logger.warning("LLM classifier failed (%r); using keyword rules", error)

        return await self.rules.route(history, message)

    async def aclose(self) -> None:
        """Close the Jev HTTP client on shutdown."""
        if isinstance(self.primary, JevClassifier):
            await self.primary.client.aclose()


def create_classifier(settings: Settings, llm: LLMProvider) -> FallbackClassifier:
    primary = None
    if settings.classifier == "jev" and not settings.typesafe_api_key:
        logger.warning("CLASSIFIER=jev but TYPESAFE_API_KEY is empty; using the LLM classifier")
    elif settings.classifier == "jev":
        primary = JevClassifier(
            api_key=settings.typesafe_api_key,
            model=settings.jev_model,
            timeout_seconds=settings.jev_timeout_seconds,
            area_threshold=settings.area_threshold,
        )
    return FallbackClassifier(
        primary=primary,
        llm_classifier=LLMClassifier(llm),
        rules=RulesClassifier(),
        min_confidence=settings.router_min_confidence,
    )


def get_classifier(request: Request) -> Classifier:
    """FastAPI dependency: the one shared classifier."""
    return request.app.state.classifier
