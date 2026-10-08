"""LLMProvider backed by LiteLLM: primary model with retry, then a fallback model."""

import logging
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

import litellm
from fastapi import Request
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, SchemaT

logger = logging.getLogger(__name__)

# LiteLLM prints a "give feedback" banner on every error; our own log line is enough.
litellm.suppress_debug_info = True

RETRIES_PER_MODEL = 2
TIMEOUT_SECONDS = 30

ResultT = TypeVar("ResultT")


class LiteLLMProvider:
    """Calls whichever provider the model strings name.

    Switching provider means changing PRIMARY_MODEL / FALLBACK_MODEL and the
    provider's API key in the environment. No code changes.
    """

    def __init__(self, primary_model: str, fallback_model: str | None = None):
        # Models are tried in this order. An empty fallback simply is not in the list.
        self.models = [model for model in (primary_model, fallback_model) if model]

    async def generate(self, messages: list[dict]) -> str:
        async def call(model: str) -> str:
            return await self._complete(model, messages)

        return await self._first_success(call)

    async def generate_json(self, messages: list[dict], schema: type[SchemaT]) -> SchemaT:
        async def call(model: str) -> SchemaT:
            # LiteLLM turns the Pydantic class into the provider's structured-output format.
            text = await self._complete(model, messages, response_format=schema)
            # Never trust the model's JSON: validate it. A bad shape counts as a failure
            # of this model, so the fallback gets a chance.
            return schema.model_validate_json(text)

        return await self._first_success(call)

    async def _first_success(self, call: Callable[[str], Awaitable[ResultT]]) -> ResultT:
        last_error: Exception | None = None
        for model in self.models:
            try:
                return await call(model)
            except Exception as error:
                logger.warning("LLM call failed on model %s: %r", model, error)
                last_error = error
        raise LLMError("No configured model produced an answer.") from last_error

    async def _complete(
        self, model: str, messages: list[dict], response_format: type[BaseModel] | None = None
    ) -> str:
        options = {}
        if response_format is not None:
            options["response_format"] = response_format
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            num_retries=RETRIES_PER_MODEL,  # retry this model (e.g. on a rate limit) before giving up on it
            timeout=TIMEOUT_SECONDS,
            **options,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError(f"Model {model} returned an empty response.")
        return content


def create_llm(settings: Settings) -> LiteLLMProvider:
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        # Send every LLM call to LangSmith as well.
        litellm.callbacks = ["langsmith"]
    return LiteLLMProvider(settings.primary_model, settings.fallback_model)


def get_llm(request: Request) -> LLMProvider:
    """FastAPI dependency: the one shared LLM provider."""
    return request.app.state.llm
