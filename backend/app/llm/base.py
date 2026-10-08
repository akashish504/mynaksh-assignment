"""The LLM interface the rest of the app depends on."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(Exception):
    """Raised when no configured model could produce a usable answer."""


class LLMProvider(Protocol):
    """Anything that can turn chat messages into text or validated JSON.

    The app only ever talks to this interface, so the provider can be swapped
    (or replaced by FakeLLM in tests) without touching the callers.
    """

    async def generate(self, messages: list[dict]) -> str: ...

    async def generate_json(self, messages: list[dict], schema: type[SchemaT]) -> SchemaT: ...
