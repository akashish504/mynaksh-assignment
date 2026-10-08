"""Classifiers and the fallback chain. No real API calls."""

from types import SimpleNamespace

import pytest

from app.classifier.base import AREA_DESCRIPTIONS, INTENT_DESCRIPTIONS, RouteResult
from app.classifier.fake import FakeClassifier
from app.classifier.jev import JevClassifier
from app.classifier.llm_classifier import LLMClassifier, RouteJSON
from app.classifier.router import FallbackClassifier, create_classifier
from app.classifier.rules import RulesClassifier
from app.config import Settings
from app.db.models import MessageRow
from app.llm.base import LLMError
from app.llm.fake import FakeLLM


def message(role: str, content: str) -> MessageRow:
    return MessageRow(role=role, content=content)


def route(intent="general", confidence=0.9, areas=("career",), durable=0.1, source="jev") -> RouteResult:
    return RouteResult(
        intent=intent,
        intent_confidence=confidence,
        areas=list(areas),
        has_durable_fact=durable,
        source=source,
    )


class FailingClassifier:
    async def route(self, history, message):
        raise TimeoutError("classifier timed out")


def make_settings(**overrides) -> Settings:
    values = dict(
        database_url="x", neo4j_uri="x", neo4j_user="x", neo4j_password="x", jwt_secret="x",
        typesafe_api_key="test-key",
    )
    return Settings(**{**values, **overrides})


# --- JevClassifier ---


class FakeJevClient:
    """Stands in for AsyncTypeSafeClient and records what it was asked."""

    def __init__(self, intent="general", confidence=0.95, nouls=None):
        self.intent = intent
        self.confidence = confidence
        self.noul_values = nouls or {}
        self.calls = []

    async def system_one(self, state, questions):
        self.calls.append((state, questions))
        nouls = {
            name: SimpleNamespace(noul=self.noul_values.get(name, 0.02))
            for name in questions
            if name != "intent"
        }
        choice = SimpleNamespace(choice=self.intent, confidence=self.confidence)
        return SimpleNamespace(choices={"intent": choice}, nouls=nouls)


def jev_with(client: FakeJevClient, area_threshold: float = 0.5) -> JevClassifier:
    classifier = JevClassifier(
        api_key="test-key", model="jev-1.13.0", timeout_seconds=3, area_threshold=area_threshold
    )
    classifier.client = client
    return classifier


async def test_jev_maps_the_answers_to_a_route_result():
    client = FakeJevClient(
        intent="general",
        confidence=0.93,
        nouls={"area_career": 0.97, "area_finance": 0.61, "area_health": 0.2, "has_durable_fact": 0.88},
    )

    result = await jev_with(client).route([], "I'm planning to switch jobs next year for better pay.")

    assert result == RouteResult(
        intent="general",
        intent_confidence=0.93,
        areas=["career", "finance"],  # health is below the 0.5 threshold
        has_durable_fact=0.88,
        source="jev",
    )


async def test_jev_asks_one_choice_and_one_noul_per_area_in_a_single_call():
    client = FakeJevClient()

    await jev_with(client).route([], "Hello")

    assert len(client.calls) == 1
    _, questions = client.calls[0]
    assert set(questions) == {"intent", "has_durable_fact"} | {f"area_{area}" for area in AREA_DESCRIPTIONS}
    assert questions["intent"].type == "choice"
    assert set(questions["intent"].criteria) == set(INTENT_DESCRIPTIONS)
    assert len(AREA_DESCRIPTIONS) == 8  # every area except "general"
    assert "area_general" not in questions
    assert questions["area_career"].type == "noul"
    assert "worth remembering" in questions["has_durable_fact"].instructions


async def test_jev_falls_back_to_the_general_area_when_no_area_qualifies():
    result = await jev_with(FakeJevClient(nouls={"area_career": 0.49})).route([], "Hmm")

    assert result.areas == ["general"]


async def test_jev_respects_the_area_threshold_setting():
    client = FakeJevClient(nouls={"area_career": 0.35})

    result = await jev_with(client, area_threshold=0.3).route([], "About work")

    assert result.areas == ["career"]


async def test_jev_sees_only_the_last_three_messages_and_the_new_one():
    history = [message("user" if n % 2 else "assistant", f"message {n}") for n in range(1, 7)]
    client = FakeJevClient()

    await jev_with(client).route(history, "Why do you say that?")

    state, _ = client.calls[0]
    assert state["new_user_message"] == "Why do you say that?"
    assert [item["content"] for item in state["recent_messages"]] == ["message 4", "message 5", "message 6"]


def test_jev_client_uses_the_pinned_model_timeout_and_no_retries(monkeypatch):
    created_with = {}

    def fake_client(**kwargs):
        created_with.update(kwargs)
        return FakeJevClient()

    monkeypatch.setattr("app.classifier.jev.AsyncTypeSafeClient", fake_client)

    JevClassifier(api_key="test-key", model="jev-1.13.0", timeout_seconds=3, area_threshold=0.5)

    assert created_with["model"] == "jev-1.13.0"
    assert created_with["timeout"] == 3
    assert created_with["retry"].max_retries == 0


# --- LLMClassifier ---


async def test_llm_classifier_maps_json_to_a_route_result():
    llm = FakeLLM(
        json_replies=[RouteJSON(intent="memory_query", intent_confidence=0.8, areas=["career"], has_durable_fact=0.05)]
    )

    result = await LLMClassifier(llm).route([message("assistant", "Earlier reply")], "What do you remember about my career?")

    assert result == RouteResult(
        intent="memory_query", intent_confidence=0.8, areas=["career"], has_durable_fact=0.05, source="llm"
    )
    # What was sent: the fixed lists, the recent message and the new message.
    sent_messages, schema = llm.json_calls[0]
    assert schema is RouteJSON
    assert "memory_query" in sent_messages[0]["content"]
    assert "spirituality" in sent_messages[0]["content"]
    assert "Earlier reply" in sent_messages[1]["content"]
    assert "What do you remember about my career?" in sent_messages[1]["content"]


async def test_llm_classifier_drops_areas_the_llm_invented():
    llm = FakeLLM(
        json_replies=[RouteJSON(intent="general", intent_confidence=0.9, areas=["career", "astronomy", "pets"], has_durable_fact=0.1)]
    )

    result = await LLMClassifier(llm).route([], "About my job and my dog")

    assert result.areas == ["career"]


async def test_llm_classifier_uses_general_when_no_valid_area_remains():
    llm = FakeLLM(json_replies=[RouteJSON(intent="smalltalk", intent_confidence=0.9, areas=[], has_durable_fact=0.0)])

    result = await LLMClassifier(llm).route([], "Hello!")

    assert result.areas == ["general"]


def test_route_json_rejects_an_unknown_intent():
    with pytest.raises(ValueError):
        RouteJSON(intent="prediction", intent_confidence=0.9, areas=[], has_durable_fact=0.1)


# --- RulesClassifier ---


@pytest.mark.parametrize(
    "text, has_history, intent, areas",
    [
        ("What should I focus on for my career?", False, "general", ["career"]),
        ("I want to save money and get a better job", False, "general", ["career", "finance"]),
        ("What do you remember about my career goals?", False, "memory_query", ["career"]),
        ("What is my zodiac sign?", False, "profile_query", ["general"]),
        ("Hello!", False, "smalltalk", ["general"]),
        ("Thanks", False, "smalltalk", ["general"]),
        ("Why do you say that?", True, "followup", ["general"]),
        ("Why do you say that?", False, "general", ["general"]),  # nothing to follow up on
        ("Should I worry about my health and sleep?", False, "general", ["health"]),
        ("Something about my network", False, "general", ["general"]),  # "network" is not "work"
    ],
)
async def test_rules_classifier(text, has_history, intent, areas):
    history = [message("assistant", "An earlier reply")] if has_history else []

    result = await RulesClassifier().route(history, text)

    assert result.intent == intent
    assert result.areas == areas
    assert result.source == "rules"
    # The memory gate is left open so extraction still runs.
    assert result.has_durable_fact == 1.0


# --- FallbackClassifier (the chain) ---


def chain(primary, llm_classifier, min_confidence=0.7) -> FallbackClassifier:
    return FallbackClassifier(primary, llm_classifier, RulesClassifier(), min_confidence)


async def test_chain_uses_jev_when_it_is_confident():
    llm_classifier = FakeClassifier(route(source="llm"))

    result = await chain(FakeClassifier(route(confidence=0.7, source="jev")), llm_classifier).route([], "career?")

    assert result.source == "jev"
    assert llm_classifier.calls == []


async def test_chain_asks_the_llm_when_jev_is_not_confident():
    jev_result = route(intent="smalltalk", confidence=0.69, areas=["general"], source="jev")
    llm_result = route(intent="general", confidence=0.85, areas=["career"], durable=0.9, source="llm")

    result = await chain(FakeClassifier(jev_result), FakeClassifier(llm_result)).route([], "career?")

    # The whole result is the LLM's, not a mix of the two.
    assert result == llm_result


async def test_chain_asks_the_llm_when_jev_fails_or_times_out():
    result = await chain(FailingClassifier(), FakeClassifier(route(source="llm"))).route([], "career?")

    assert result.source == "llm"


async def test_chain_uses_rules_when_the_llm_fails_too():
    result = await chain(FailingClassifier(), FailingClassifier()).route([], "What about my career?")

    assert result.source == "rules"
    assert result.areas == ["career"]
    assert result.has_durable_fact == 1.0


async def test_chain_uses_rules_when_jev_is_unsure_and_the_llm_fails():
    result = await chain(FakeClassifier(route(confidence=0.2)), FailingClassifier()).route([], "Hello")

    assert result.source == "rules"


async def test_chain_skips_jev_when_there_is_no_primary():
    llm_classifier = FakeClassifier(route(source="llm"))

    result = await chain(None, llm_classifier).route([], "career?")

    assert result.source == "llm"
    assert len(llm_classifier.calls) == 1


async def test_llm_classifier_failure_reaches_rules_through_a_real_llm_error():
    llm = FakeLLM()
    llm.fail = True

    result = await chain(None, LLMClassifier(llm)).route([], "Tell me about travel")

    assert result.source == "rules"
    assert result.areas == ["travel"]


# --- create_classifier (settings decide the chain) ---


def test_classifier_jev_setting_makes_jev_the_primary():
    classifier = create_classifier(make_settings(classifier="jev", jev_model="jev-1.13.0"), FakeLLM())

    assert isinstance(classifier.primary, JevClassifier)
    assert isinstance(classifier.llm_classifier, LLMClassifier)
    assert classifier.min_confidence == 0.7


def test_classifier_llm_setting_skips_jev():
    classifier = create_classifier(make_settings(classifier="llm"), FakeLLM())

    assert classifier.primary is None
    assert isinstance(classifier.llm_classifier, LLMClassifier)


def test_jev_without_an_api_key_starts_without_jev():
    classifier = create_classifier(make_settings(classifier="jev", typesafe_api_key=""), FakeLLM())

    assert classifier.primary is None


def test_unknown_classifier_setting_is_rejected():
    with pytest.raises(ValueError):
        make_settings(classifier="magic")
