"""The chat pipeline: context selection, prompt, saving, and failure handling.

FakeLLM and FakeClassifier are used throughout, so the tests assert on what is
SENT to the LLM (the prompt blocks) and on `context_used`, never on generated wording.
"""

import uuid

from sqlalchemy import select

from app.brain.memory_repository import MemoryRepository
from app.chat.pipeline import LLM_FAILURE_REPLY
from app.config import get_settings
from app.db.models import MessageRow
from app.main import app
from tests.conftest import (
    BrokenNeo4jDriver,
    add_memory,
    ask,
    extraction,
    new_session,
    onboard,
    prompt_text,
    route,
    signup,
    user_id_of,
)

GOAL_TEXT = "Career goal: plans to switch jobs in 2027."


async def saved_messages(session_id: str) -> list[MessageRow]:
    async with app.state.session_factory() as db:
        result = await db.execute(
            select(MessageRow)
            .where(MessageRow.session_id == uuid.UUID(session_id))
            .order_by(MessageRow.created_at)
        )
        return list(result.scalars())


# =============================================================================
# The assignment's scenarios covered in this phase: 1, 3, 4, 6, 8
# =============================================================================


async def test_scenario_1_new_user_gets_a_generic_answer_with_a_nudge(client, fake_llm, fake_classifier):
    headers = await signup(client)  # no profile, no memories
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"])]

    body = await ask(client, headers, session_id, "What should I focus on in my career?")

    assert body["response"] == "FAKE REPLY"
    assert body["type"] == "answer"
    assert body["options"] is None
    assert body["context_used"] == []
    prompt = prompt_text(fake_llm)
    assert "has not completed their birth details" in prompt
    assert "suggest they complete their birth details" in prompt
    assert "[PROFILE]" not in prompt
    assert "[MEMORY]" not in prompt
    assert "[USER]\nWhat should I focus on in my career?" in prompt
    # No sign is known, so the model is told not to make one up.
    assert "Do not name, guess or imply any zodiac sign" in prompt


async def test_scenario_3_a_stored_memory_is_retrieved_for_a_related_question(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    goal_id = await add_memory(headers, GOAL_TEXT, kind="goal", life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"])]

    body = await ask(client, headers, session_id, "What should I focus on for my career?")

    assert body["context_used"] == ["user_profile", "zodiac", f"goal:{goal_id}"]
    prompt = prompt_text(fake_llm)
    assert f"[MEMORY]\n- goal (career): {GOAL_TEXT} (stated today)" in prompt
    assert "Name: Rahul" in prompt
    assert "Sun sign: Leo (Fire) - traits: confident, generous, expressive" in prompt
    assert "has not completed their birth details" not in prompt
    assert "Do not name, guess or imply any zodiac sign" not in prompt  # the sign is known here


async def test_scenario_4_a_follow_up_reuses_the_previous_turns_memories(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    goal_id = await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"]), route("followup", ["career"])]

    first = await ask(client, headers, session_id, "What should I focus on for my career?")
    # A newer, stronger career memory appears between the two turns. A new search would
    # pick it up; a follow-up must not, because it reuses the previous turn's memories.
    await add_memory(headers, "Career: was just promoted to team lead.", life_area="career", importance=1.0, confidence=1.0)
    second = await ask(client, headers, session_id, "Why do you say that?")

    assert first["context_used"] == ["user_profile", "zodiac", f"goal:{goal_id}"]
    assert second["context_used"] == ["user_profile", "zodiac", "history", f"goal:{goal_id}"]
    prompt = prompt_text(fake_llm)
    assert GOAL_TEXT in prompt
    assert "promoted to team lead" not in prompt
    # The short-term context carries the conversation so far.
    assert "[HISTORY]\nuser: What should I focus on for my career?\nassistant: FAKE REPLY" in prompt
    assert "[USER]\nWhy do you say that?" in prompt


async def test_scenario_6_an_irrelevant_memory_is_not_included(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    goal_id = await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["health"])]

    body = await ask(client, headers, session_id, "How can I sleep better?")

    assert f"goal:{goal_id}" not in body["context_used"]
    assert body["context_used"] == ["user_profile", "zodiac"]
    prompt = prompt_text(fake_llm)
    assert "[MEMORY]" not in prompt
    assert GOAL_TEXT not in prompt


async def test_scenario_8_missing_information_is_marked_unknown_not_invented(client, fake_llm, fake_classifier):
    # Profile exists, but the birth time is unknown and nothing is stored about a partner.
    headers = await onboard(client, birth_time_known=False)
    await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["relationships"]), route("general", ["career"])]

    partner = await ask(client, headers, session_id, "What's my partner's name?")
    partner_prompt = prompt_text(fake_llm)
    timing = await ask(client, headers, session_id, "At what exact time of day should I sign my new job contract?")
    timing_prompt = prompt_text(fake_llm)

    # Nothing about a partner is stored, so no memory is sent and the rules forbid inventing one.
    assert partner["context_used"] == ["user_profile", "zodiac"]
    assert "[MEMORY]" not in partner_prompt
    assert "Never invent facts about the user." in partner_prompt
    assert "say that you don't know it yet" in partner_prompt
    # The unknown birth time is stated as unknown, with the rule about timing.
    assert "Birth time: unknown" in timing_prompt
    assert 'If the birth time is "unknown", do not give timing that depends on it' in timing_prompt
    assert "user_profile" in timing["context_used"]


# =============================================================================
# Request and response
# =============================================================================


async def test_response_has_the_documented_shape(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)

    body = await ask(client, headers, session_id, "Hello there")

    assert set(body) == {"response", "user_id", "session_id", "message_id", "type", "options", "context_used"}
    assert body["user_id"] == user_id_of(headers)
    assert body["session_id"] == session_id
    # message_id is the USER message's id.
    user_message = (await saved_messages(session_id))[0]
    assert body["message_id"] == str(user_message.id)
    assert user_message.role == "user"


async def test_user_id_in_the_body_is_ignored(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)

    response = await client.post(
        "/chat",
        json={"user_id": "user-123", "session_id": session_id, "message": "What should I focus on in my career?"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == user_id_of(headers)


async def test_invalid_requests_are_rejected(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)

    empty = await client.post("/chat", json={"session_id": session_id, "message": "   "}, headers=headers)
    too_long = await client.post("/chat", json={"session_id": session_id, "message": "x" * 2001}, headers=headers)
    longest_allowed = await client.post("/chat", json={"session_id": session_id, "message": "x" * 2000}, headers=headers)
    no_session = await client.post("/chat", json={"message": "Hello"}, headers=headers)
    bad_session = await client.post("/chat", json={"session_id": "session-456", "message": "Hello"}, headers=headers)

    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert longest_allowed.status_code == 200
    assert no_session.status_code == 422  # session_id is required; sessions are never auto-created
    assert bad_session.status_code == 422


async def test_chat_requires_a_token(client):
    response = await client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": "Hello"})

    assert response.status_code == 401


async def test_another_users_session_returns_404_and_saves_nothing(client, fake_llm, fake_classifier):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com")
    rahul_session = await new_session(client, rahul)

    response = await client.post("/chat", json={"session_id": rahul_session, "message": "Hello"}, headers=priya)
    missing = await client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": "Hello"}, headers=priya)

    assert response.status_code == 404
    assert missing.status_code == 404
    assert await saved_messages(rahul_session) == []
    assert fake_llm.calls == []


async def test_one_user_never_gets_another_users_memories(client, fake_llm, fake_classifier):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com", name="Priya")
    await add_memory(rahul, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, priya)
    fake_classifier.results = [route("memory_query", ["general"])]

    body = await ask(client, priya, session_id, "What do you remember about me?")

    assert body["context_used"] == ["user_profile", "zodiac"]
    assert GOAL_TEXT not in prompt_text(fake_llm)
    assert "Name: Priya" in prompt_text(fake_llm)


# =============================================================================
# Retrievers, one per intent
# =============================================================================


async def test_general_ranks_by_confidence_importance_and_recency_and_keeps_top_k(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    # Scores: A = 0.9 x 0.9 = 0.81 (fresh), B = 1.0 x 1.0 x exp(-180/90) = 0.14 (old),
    #         C = 0.5 x 0.5 = 0.25, D-H = 0.6 x 0.6 = 0.36 each.
    strong = await add_memory(headers, "A: strong and fresh.", confidence=0.9, importance=0.9)
    old = await add_memory(headers, "B: perfect but 180 days old.", confidence=1.0, importance=1.0, days_old=180)
    weak = await add_memory(headers, "C: weak.", confidence=0.5, importance=0.5)
    middle = [await add_memory(headers, f"Middle memory {n}.", confidence=0.6, importance=0.6) for n in range(4)]
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"])]

    body = await ask(client, headers, session_id, "Career advice?")

    memory_labels = [label for label in body["context_used"] if ":" in label]
    assert len(memory_labels) == 5  # TOP_K_MEMORIES
    assert memory_labels[0] == f"goal:{strong}"  # highest score first
    assert set(memory_labels[1:]) == {f"goal:{memory_id}" for memory_id in middle}
    # Recency decay pushed the old one out, and the weak one did not make the cut.
    assert f"goal:{old}" not in memory_labels
    assert f"goal:{weak}" not in memory_labels


async def test_general_uses_every_routed_area(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    career = await add_memory(headers, GOAL_TEXT, life_area="career")
    finance = await add_memory(headers, "Finance: saving for a house.", kind="memory", life_area="finance")
    await add_memory(headers, "Health: runs every morning.", kind="interest", life_area="health")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career", "finance"])]

    body = await ask(client, headers, session_id, "Should I change jobs for more money?")

    assert set(body["context_used"]) == {"user_profile", "zodiac", f"goal:{career}", f"memory:{finance}"}


async def test_superseded_memories_are_never_selected(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    await add_memory(headers, "Career goal: plans to switch jobs in 2026.", status="superseded")
    current = await add_memory(headers, GOAL_TEXT)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"]), route("memory_query", ["career"])]

    general = await ask(client, headers, session_id, "Career advice?")
    memory_query = await ask(client, headers, session_id, "What do you remember about my career?")

    assert [label for label in general["context_used"] if ":" in label] == [f"goal:{current}"]
    assert [label for label in memory_query["context_used"] if ":" in label] == [f"goal:{current}"]
    assert "switch jobs in 2026" not in prompt_text(fake_llm)


async def test_general_with_no_area_falls_back_to_the_three_most_important(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    top = await add_memory(headers, "Most important.", life_area="career", importance=0.95)
    second = await add_memory(headers, "Second.", life_area="health", importance=0.9)
    third = await add_memory(headers, "Third.", life_area="family", importance=0.85)
    fourth = await add_memory(headers, "Fourth.", life_area="travel", importance=0.2)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["general"])]

    body = await ask(client, headers, session_id, "What does this year hold for me?")

    assert [label for label in body["context_used"] if ":" in label] == [f"goal:{top}", f"goal:{second}", f"goal:{third}"]
    assert f"goal:{fourth}" not in body["context_used"]


async def test_general_area_with_its_own_memories_uses_those(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    general = await add_memory(headers, "Prefers short answers.", kind="preference", life_area="general", importance=0.3)
    await add_memory(headers, GOAL_TEXT, life_area="career", importance=1.0)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["general"])]

    body = await ask(client, headers, session_id, "Any thoughts for me?")

    assert [label for label in body["context_used"] if ":" in label] == [f"preference:{general}"]


async def test_followup_without_a_previous_reply_is_treated_as_general(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    goal_id = await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("followup", ["career"])]

    body = await ask(client, headers, session_id, "Why do you say that?")

    assert body["context_used"] == ["user_profile", "zodiac", f"goal:{goal_id}"]
    assistant = (await saved_messages(session_id))[1]
    assert assistant.route_intent == "general"  # stored as what it was handled as


async def test_followup_skips_a_memory_deleted_since(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    kept = await add_memory(headers, GOAL_TEXT, life_area="career", importance=0.9)
    deleted = await add_memory(headers, "Career: wants to move into management.", life_area="career", importance=0.5)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"]), route("followup", ["career"])]

    first = await ask(client, headers, session_id, "Career advice?")
    await app.state.neo4j.execute_query("MATCH (m {id: $id}) DETACH DELETE m", id=deleted)
    second = await ask(client, headers, session_id, "Why do you say that?")

    assert first["context_used"] == ["user_profile", "zodiac", f"goal:{kept}", f"goal:{deleted}"]
    assert second["context_used"] == ["user_profile", "zodiac", "history", f"goal:{kept}"]


async def test_memory_query_returns_everything_in_the_area_newest_first_without_astrology(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    oldest = await add_memory(headers, "Oldest career memory.", life_area="career", days_old=40, importance=0.1, confidence=0.1)
    newest = await add_memory(headers, "Newest career memory.", kind="memory", life_area="career", days_old=1)
    middle = [await add_memory(headers, f"Career memory {n}.", life_area="career", days_old=10 + n) for n in range(5)]
    await add_memory(headers, "Health: runs every morning.", life_area="health")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("memory_query", ["career"])]

    body = await ask(client, headers, session_id, "What do you remember about my career goals?")

    memory_labels = [label for label in body["context_used"] if ":" in label]
    # All 7 career memories (more than TOP_K), newest first, low scores included.
    assert memory_labels == [f"memory:{newest}"] + [f"goal:{memory_id}" for memory_id in middle] + [f"goal:{oldest}"]
    assert body["context_used"][:2] == ["user_profile", "zodiac"]
    prompt = prompt_text(fake_llm)
    assert "runs every morning" not in prompt
    # Profile facts and the sign NAME are included, but no traits and no astrology rule.
    assert "Name: Rahul" in prompt
    assert "Date of birth: 1995-08-15" in prompt
    assert "Sun sign: Leo" in prompt
    assert "traits" not in prompt
    assert "Fire" not in prompt
    assert "astrology guide" not in prompt
    assert "Do not add astrological interpretation." in prompt
    assert "(stated yesterday)" in prompt
    assert "(stated 1 month ago)" in prompt


async def test_memory_query_about_everything_returns_all_areas(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    career = await add_memory(headers, GOAL_TEXT, life_area="career", days_old=2)
    health = await add_memory(headers, "Health: runs every morning.", kind="interest", life_area="health", days_old=1)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("memory_query", ["general"])]

    body = await ask(client, headers, session_id, "What do you remember about me?")

    assert body["context_used"] == ["user_profile", "zodiac", f"interest:{health}", f"goal:{career}"]


async def test_profile_query_sends_profile_and_zodiac_only(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("profile_query", ["career"])]

    body = await ask(client, headers, session_id, "What is my zodiac sign?")

    assert body["context_used"] == ["user_profile", "zodiac"]
    prompt = prompt_text(fake_llm)
    assert "[MEMORY]" not in prompt
    assert "Birth place: Delhi" in prompt
    assert "Birth time: 14:30" in prompt
    assert "Sun sign: Leo (Fire)" in prompt


async def test_smalltalk_sends_only_the_name_and_the_last_two_messages(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["health"]), route("general", ["health"]), route("smalltalk", ["general"])]
    await ask(client, headers, session_id, "First question")
    await ask(client, headers, session_id, "Second question")

    body = await ask(client, headers, session_id, "Thanks!")

    assert body["context_used"] == ["user_profile", "history"]  # no "zodiac", no memories
    prompt = prompt_text(fake_llm)
    assert "[PROFILE]\nName: Rahul" in prompt
    assert "Date of birth" not in prompt
    assert "Sun sign: Leo" not in prompt
    assert "[MEMORY]" not in prompt
    # Only the last 2 of the 4 earlier messages.
    assert "[HISTORY]\nuser: Second question\nassistant: FAKE REPLY\n\n[USER]\nThanks!" in prompt
    assert "First question" not in prompt


# =============================================================================
# Prompt and short-term context
# =============================================================================


async def test_history_is_limited_to_the_last_six_messages_of_this_session(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    other_session = await new_session(client, headers)
    session_id = await new_session(client, headers)
    await ask(client, headers, other_session, "A message in another chat")
    for number in range(1, 5):
        await ask(client, headers, session_id, f"Question {number}")

    body = await ask(client, headers, session_id, "Question 5")

    prompt = prompt_text(fake_llm)
    assert "history" in body["context_used"]
    # 8 earlier messages exist in this session; only the last 6 (questions 2-4 and replies) are sent.
    assert "Question 1" not in prompt
    assert prompt.count("assistant: FAKE REPLY") == 3
    assert "user: Question 2" in prompt
    assert "A message in another chat" not in prompt


async def test_first_message_has_no_history_block_or_label(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)

    body = await ask(client, headers, session_id, "Hello")

    assert "history" not in body["context_used"]
    assert "[HISTORY]" not in prompt_text(fake_llm)


async def test_system_prompt_has_todays_date_and_the_no_clarifying_rule(client, fake_llm, fake_classifier):
    from datetime import datetime, timezone

    headers = await onboard(client)
    session_id = await new_session(client, headers)

    await ask(client, headers, session_id, "What about next month?")

    system = fake_llm.calls[-1][0]
    assert system["role"] == "system"
    assert system["content"].startswith("[SYSTEM]\nYou are a warm, practical astrology guide")
    assert f"Today's date is {datetime.now(timezone.utc).date().isoformat()} (UTC)." in system["content"]
    assert "Do not ask clarifying questions. Make a reasonable assumption and state it briefly." in system["content"]
    assert "ask one short clarifying question" not in system["content"]
    assert "Never mention them to the user" in system["content"]
    assert "Reply in plain text without Markdown, in at most about 120 words." in system["content"]
    assert fake_llm.calls[-1][1]["role"] == "user"


async def test_the_classifier_sees_the_history_and_the_new_message(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    await ask(client, headers, session_id, "First question")

    await ask(client, headers, session_id, "Why do you say that?")

    history, message = fake_classifier.calls[-1]
    assert message == "Why do you say that?"
    assert [row.content for row in history] == ["First question", "FAKE REPLY"]


# =============================================================================
# Saving
# =============================================================================


async def test_both_messages_are_saved_with_their_fields(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    goal_id = await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"], durable=0.9)]
    fake_llm.json_replies = [extraction()]  # the memory task finds nothing new to store

    body = await ask(client, headers, session_id, "I'm planning to switch jobs next year.")

    user_message, assistant_message = await saved_messages(session_id)
    assert user_message.role == "user"
    assert user_message.content == "I'm planning to switch jobs next year."
    # The gate score 0.9 is above 0.5, so the memory task ran and finished.
    assert user_message.memory_status == "done"
    assert user_message.type is None and user_message.context_used is None
    assert assistant_message.role == "assistant"
    assert assistant_message.content == "FAKE REPLY"
    assert assistant_message.type == "answer"
    assert assistant_message.context_used == body["context_used"]
    assert assistant_message.used_memory_ids == [goal_id]
    assert assistant_message.route_intent == "general"
    assert assistant_message.route_areas == ["career"]
    assert assistant_message.memory_status is None
    assert user_message.created_at < assistant_message.created_at
    assert str(user_message.user_id) == user_id_of(headers)


async def test_memory_gate_marks_low_scoring_messages_as_skipped(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route(durable=0.49), route(durable=0.5)]
    fake_llm.json_replies = [extraction()]

    await ask(client, headers, session_id, "What should I focus on?")
    await ask(client, headers, session_id, "I am a vegetarian.")

    messages = await saved_messages(session_id)
    # Below the threshold: skipped, and extraction never ran. At the threshold: processed.
    assert [m.memory_status for m in messages if m.role == "user"] == ["skipped", "done"]
    assert len(fake_llm.json_calls) == 1


async def test_memory_gate_can_be_switched_off(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route(durable=0.01)]
    fake_llm.json_replies = [extraction()]
    settings = get_settings().model_copy(update={"memory_gate_enabled": False})
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        await ask(client, headers, session_id, "Hello")
    finally:
        app.dependency_overrides.clear()

    # With the gate off, even a low score goes to extraction.
    assert (await saved_messages(session_id))[0].memory_status == "done"
    assert len(fake_llm.json_calls) == 1


async def test_session_title_comes_from_the_first_message_only(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    first_message = "What should I focus on for my career over the next twelve months, given my goals?"

    await ask(client, headers, session_id, first_message)
    sessions_after_first = (await client.get("/sessions", headers=headers)).json()
    await ask(client, headers, session_id, "A second message")
    sessions_after_second = (await client.get("/sessions", headers=headers)).json()

    assert sessions_after_first[0]["title"] == first_message[:60]
    assert len(sessions_after_first[0]["title"]) == 60
    assert sessions_after_second[0]["title"] == first_message[:60]


async def test_chatting_moves_the_session_to_the_top_of_the_list(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    older = await new_session(client, headers)
    newer = await new_session(client, headers)

    await ask(client, headers, older, "Hello again")

    sessions = (await client.get("/sessions", headers=headers)).json()
    assert [session["id"] for session in sessions] == [older, newer]


async def test_messages_endpoint_shows_the_saved_turn(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)

    body = await ask(client, headers, session_id, "Hello")

    listed = (await client.get(f"/sessions/{session_id}/messages", headers=headers)).json()
    assert [(m["role"], m["content"]) for m in listed] == [("user", "Hello"), ("assistant", "FAKE REPLY")]
    assert listed[0]["id"] == body["message_id"]
    assert listed[1]["context_used"] == body["context_used"]


# =============================================================================
# Failures
# =============================================================================


async def test_llm_failure_returns_a_friendly_reply_and_still_saves_the_turn(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"], durable=0.9)]
    fake_llm.fail = True

    response = await client.post("/chat", json={"session_id": session_id, "message": "Career advice?"}, headers=headers)

    assert response.status_code == 200  # never an error page or a stack trace
    body = response.json()
    assert body["response"] == LLM_FAILURE_REPLY
    assert body["type"] == "answer"
    assert body["context_used"] == []
    assert "Traceback" not in response.text
    user_message, assistant_message = await saved_messages(session_id)
    assert assistant_message.content == LLM_FAILURE_REPLY
    assert assistant_message.context_used == []
    assert assistant_message.used_memory_ids == []
    # The gate passed, so extraction was still attempted; the LLM is down, so it failed.
    assert len(fake_llm.json_calls) == 1
    assert user_message.memory_status == "failed"


async def test_neo4j_down_answers_from_history_only(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    await add_memory(headers, GOAL_TEXT, life_area="career")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"], durable=0.9)]
    await ask(client, headers, session_id, "First question")

    real_driver = app.state.neo4j
    app.state.neo4j = BrokenNeo4jDriver()
    try:
        first_turn_session = await new_session(client, headers)
        no_history = await ask(client, headers, first_turn_session, "Career advice?")
        with_history = await ask(client, headers, session_id, "Career advice?")
    finally:
        app.state.neo4j = real_driver

    assert with_history["response"] == "FAKE REPLY"
    assert with_history["context_used"] == ["history"]
    assert no_history["context_used"] == []
    prompt = prompt_text(fake_llm)
    assert "[PROFILE]" not in prompt
    assert "[MEMORY]" not in prompt
    assert "[HISTORY]\nuser: First question" in prompt
    # The profile IS complete; we just could not read it, so there is no nudge.
    assert "has not completed their birth details" not in prompt
    # With no profile to read, the sign is unknown for this turn and must not be guessed.
    assert "Do not name, guess or imply any zodiac sign" in prompt
    # Memory extraction is skipped and recorded as failed, even though the gate passed.
    assert (await saved_messages(session_id))[2].memory_status == "failed"


async def test_neo4j_failing_only_during_retrieval_is_handled_the_same_way(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"], durable=0.9)]

    class FailsOnMemories(MemoryRepository):
        async def get_active_by_areas(self, user_id, areas):
            raise ConnectionError("Neo4j dropped the connection")

    from app.brain.memory_repository import get_memory_repository

    app.dependency_overrides[get_memory_repository] = lambda: FailsOnMemories(app.state.neo4j)
    try:
        body = await ask(client, headers, session_id, "Career advice?")
    finally:
        app.dependency_overrides.clear()

    assert body["response"] == "FAKE REPLY"
    assert body["context_used"] == []
    assert (await saved_messages(session_id))[0].memory_status == "failed"


async def test_postgres_down_returns_503(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    from app.db.engine import create_engine, create_session_factory

    real_factory = app.state.session_factory
    app.state.session_factory = create_session_factory(create_engine("postgresql://nobody:nothing@localhost:1/none"))
    try:
        response = await client.post("/chat", json={"session_id": session_id, "message": "Hello"}, headers=headers)
    finally:
        app.state.session_factory = real_factory

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]
    assert fake_llm.calls == []


async def test_partial_profile_from_chat_is_used_and_still_nudges(client, fake_llm, fake_classifier):
    """A profile can exist in Neo4j before onboarding is complete (built from chat)."""
    headers = await signup(client)
    await app.state.neo4j.execute_query(
        "MATCH (u:User {id: $id}) SET u.name = 'Rahul'", id=user_id_of(headers)
    )
    session_id = await new_session(client, headers)

    body = await ask(client, headers, session_id, "Any guidance for me?")

    assert body["context_used"] == ["user_profile"]
    prompt = prompt_text(fake_llm)
    assert "Name: Rahul" in prompt
    assert "Birth time: unknown" in prompt
    assert "has not completed their birth details" in prompt
