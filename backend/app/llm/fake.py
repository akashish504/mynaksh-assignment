"""A deterministic LLM for tests. It never calls a real API."""

from pydantic import BaseModel

from app.llm.base import LLMError, SchemaT


class FakeLLM:
    """Returns scripted answers and records every call it receives.

    Tests assert on `calls` (what was sent to the LLM), not on generated wording.
    """

    def __init__(self, reply: str = "FAKE REPLY", json_replies: list[BaseModel | Exception] | None = None):
        self.reply = reply
        # Answers for generate_json, used in order.
        self.json_replies = list(json_replies or [])
        # Set to True to make every call fail, as if all models were down.
        self.fail = False
        self.calls: list[list[dict]] = []
        self.json_calls: list[tuple[list[dict], type[BaseModel]]] = []

    async def generate(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if self.fail:
            raise LLMError("FakeLLM is set to fail.")
        return self.reply

    async def generate_json(self, messages: list[dict], schema: type[SchemaT]) -> SchemaT:
        self.json_calls.append((messages, schema))
        if self.fail or not self.json_replies:
            raise LLMError("FakeLLM has no JSON reply to give.")
        reply = self.json_replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
