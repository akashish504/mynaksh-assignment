"""LiteLLMProvider: retry settings, fallback order, JSON validation. No real API calls."""

from types import SimpleNamespace

import litellm
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm.base import LLMError
from app.llm.fake import FakeLLM
from app.llm.litellm_provider import LiteLLMProvider, create_llm

MESSAGES = [{"role": "user", "content": "Hello"}]


class Answer(BaseModel):
    city: str
    year: int


def fake_response(content: str | None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def litellm_calls(monkeypatch):
    """Replace litellm.acompletion. `behaviour` maps a model name to a reply or an exception."""
    calls = []
    behaviour = {}

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        outcome = behaviour[kwargs["model"]]
        if isinstance(outcome, Exception):
            raise outcome
        return fake_response(outcome)

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls, behaviour


async def test_generate_uses_the_primary_model(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = "Hello Rahul"

    reply = await LiteLLMProvider("primary", "fallback").generate(MESSAGES)

    assert reply == "Hello Rahul"
    assert [call["model"] for call in calls] == ["primary"]
    assert calls[0]["messages"] == MESSAGES
    assert calls[0]["num_retries"] == 2  # the primary is retried before falling back
    assert calls[0]["timeout"] == 30


async def test_generate_falls_back_when_the_primary_fails(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = RuntimeError("rate limited")
    behaviour["fallback"] = "Answer from the fallback"

    reply = await LiteLLMProvider("primary", "fallback").generate(MESSAGES)

    assert reply == "Answer from the fallback"
    assert [call["model"] for call in calls] == ["primary", "fallback"]


async def test_generate_raises_llm_error_when_both_models_fail(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = RuntimeError("down")
    behaviour["fallback"] = RuntimeError("also down")

    with pytest.raises(LLMError):
        await LiteLLMProvider("primary", "fallback").generate(MESSAGES)

    assert [call["model"] for call in calls] == ["primary", "fallback"]


async def test_without_a_fallback_model_only_the_primary_is_tried(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = RuntimeError("down")

    with pytest.raises(LLMError):
        await LiteLLMProvider("primary", "").generate(MESSAGES)

    assert [call["model"] for call in calls] == ["primary"]


async def test_an_empty_reply_counts_as_a_failure(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = None
    behaviour["fallback"] = "Real answer"

    reply = await LiteLLMProvider("primary", "fallback").generate(MESSAGES)

    assert reply == "Real answer"


async def test_generate_json_returns_a_validated_object(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = '{"city": "Delhi", "year": 1995}'

    answer = await LiteLLMProvider("primary").generate_json(MESSAGES, Answer)

    assert answer == Answer(city="Delhi", year=1995)
    assert calls[0]["response_format"] is Answer


async def test_generate_json_falls_back_when_the_primary_returns_invalid_json(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = '{"city": "Delhi"}'  # "year" is missing
    behaviour["fallback"] = '{"city": "Delhi", "year": 1995}'

    answer = await LiteLLMProvider("primary", "fallback").generate_json(MESSAGES, Answer)

    assert answer.year == 1995
    assert [call["model"] for call in calls] == ["primary", "fallback"]


async def test_generate_json_raises_llm_error_when_no_model_returns_valid_json(litellm_calls):
    calls, behaviour = litellm_calls
    behaviour["primary"] = "not json at all"

    with pytest.raises(LLMError):
        await LiteLLMProvider("primary").generate_json(MESSAGES, Answer)


def test_provider_is_chosen_by_settings_only():
    """Switching provider = changing env values. No code change."""
    settings = Settings(
        database_url="x", neo4j_uri="x", neo4j_user="x", neo4j_password="x", jwt_secret="x",
        primary_model="gemini/some-model", fallback_model="openai/some-model",
    )

    assert create_llm(settings).models == ["gemini/some-model", "openai/some-model"]


async def test_fake_llm_records_calls_and_can_fail():
    llm = FakeLLM(reply="scripted", json_replies=[Answer(city="Delhi", year=1995)])

    assert await llm.generate(MESSAGES) == "scripted"
    assert await llm.generate_json(MESSAGES, Answer) == Answer(city="Delhi", year=1995)
    assert llm.calls == [MESSAGES]
    assert llm.json_calls == [(MESSAGES, Answer)]

    llm.fail = True
    with pytest.raises(LLMError):
        await llm.generate(MESSAGES)
