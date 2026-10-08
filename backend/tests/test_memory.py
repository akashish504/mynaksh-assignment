"""The background memory task, memory polling and the memory page.

The extraction LLM is FakeLLM with scripted JSON, so these tests check what the
task DOES with an extraction result, and what was SENT to the extraction LLM.
"""

import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.db.memory_event_repository import MemoryEventRepository
from app.db.models import MemoryEventRow, MessageRow
from app.main import app
from app.memory.task import MemoryTask
from tests.conftest import (
    BrokenNeo4jDriver,
    add_memory,
    ask,
    extracted,
    extraction,
    new_session,
    onboard,
    profile_correction,
    prompt_text,
    route,
    signup,
    user_id_of,
)

SWITCH_JOBS = "I'm planning to switch jobs next year."
NEXT_YEAR = date.today().year + 1


async def memory_nodes(headers: dict) -> list[dict]:
    """Every memory node of the user, with its label and the life area it is ABOUT."""
    records, _, _ = await app.state.neo4j.execute_query(
        "MATCH (u:User {id: $id})-[r]->(m)-[:ABOUT]->(a:LifeArea) "
        "RETURN m, labels(m)[0] AS label, type(r) AS relationship, a.name AS area "
        "ORDER BY m.created_at",
        id=user_id_of(headers),
    )
    return [
        {**dict(r["m"]), "label": r["label"], "relationship": r["relationship"], "area": r["area"]}
        for r in records
    ]


async def events_for(message_id: str) -> list[MemoryEventRow]:
    async with app.state.session_factory() as db:
        return await MemoryEventRepository(db).list_for_message(uuid.UUID(message_id))


async def status_of(message_id: str) -> str:
    async with app.state.session_factory() as db:
        return (await db.get(MessageRow, uuid.UUID(message_id))).memory_status


async def updates(client, headers, message_id: str) -> dict:
    response = await client.get(f"/messages/{message_id}/memory-updates", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def durable(areas=("career",), intent="general"):
    """A route whose gate score lets the message through to extraction."""
    return route(intent, areas, durable=0.9)


# =============================================================================
# The assignment's scenarios covered in this phase: 2, 5, 7
# =============================================================================


async def test_scenario_2_a_lasting_fact_becomes_a_goal_node(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [
        extraction(
            extracted(
                text=f"Career goal: plans to switch jobs in {NEXT_YEAR}.",
                attributes={"target_year": NEXT_YEAR, "timeframe": "next year"},
            )
        )
    ]

    body = await ask(client, headers, session_id, SWITCH_JOBS)

    # --- the graph: a Goal node, linked from the User and ABOUT the career life area ---
    nodes = await memory_nodes(headers)
    assert len(nodes) == 1
    goal = nodes[0]
    assert goal["label"] == "Goal"
    assert goal["relationship"] == "HAS_GOAL"
    assert goal["area"] == "career"
    assert goal["kind"] == "goal"
    assert goal["life_area"] == "career"
    assert goal["text"] == f"Career goal: plans to switch jobs in {NEXT_YEAR}."
    assert json.loads(goal["attributes"]) == {"target_year": NEXT_YEAR, "timeframe": "next year"}
    assert goal["status"] == "active"
    assert goal.get("superseded_by") is None  # Neo4j does not store a null property at all
    assert goal["confidence"] == 0.9 and goal["importance"] == 0.8
    # It points back to the Postgres message and session it came from.
    assert goal["source_message_id"] == body["message_id"]
    assert goal["source_session_id"] == session_id

    # --- Postgres: one audit row, and the message is marked done ---
    events = await events_for(body["message_id"])
    assert len(events) == 1
    assert events[0].action == "created"
    assert events[0].memory_id == goal["id"]
    assert (events[0].kind, events[0].title, events[0].life_area) == ("goal", "Switch jobs", "career")
    assert await status_of(body["message_id"]) == "done"

    # --- the polling endpoint the frontend uses for the "memory updated" chip ---
    assert await updates(client, headers, body["message_id"]) == {
        "status": "done",
        "updates": [
            {"action": "created", "kind": "goal", "title": "Switch jobs", "life_area": "career", "memory_id": goal["id"]}
        ],
    }

    # --- the chat reply itself did not wait for or depend on any of this ---
    assert body["response"] == "FAKE REPLY"
    assert f"goal:{goal['id']}" not in body["context_used"]


async def test_scenario_2_what_the_extraction_llm_is_sent(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    existing = await add_memory(headers, "Health: runs every morning.", kind="interest", life_area="health")
    session_id = await new_session(client, headers)
    fake_classifier.results = [route(durable=0.1), durable()]
    fake_llm.json_replies = [extraction()]
    await ask(client, headers, session_id, "Hello")

    await ask(client, headers, session_id, SWITCH_JOBS)

    messages, schema = fake_llm.json_calls[0]
    system, user = messages[0]["content"], messages[1]["content"]
    today = datetime.now(timezone.utc).date()
    # Today's date, so "next year" can be turned into a year.
    assert f"Today's date is {today.isoformat()} (UTC)." in system
    assert f'"next year" is {today.year + 1}' in system
    # The store / do-not-store rules and the closed list of life areas.
    assert "STORE: stable facts, goals, preferences, interests, significant life events." in system
    assert "DO NOT STORE: greetings, questions, passing moods, the assistant's own statements or predictions." in system
    assert "career, finance, relationships, family, health, education, spirituality, travel, general" in system
    # The new message, the two messages before it, the existing memories and the profile.
    assert f"NEW USER MESSAGE:\n{SWITCH_JOBS}" in user
    assert "RECENT MESSAGES:\nuser: Hello\nassistant: FAKE REPLY" in user
    assert f"{existing} | interest | health | Health: runs every morning." in user
    assert "name: Rahul" in user and "dob: 1995-08-15" in user and "birth_place: Delhi" in user


async def test_scenario_5_a_new_session_uses_what_was_remembered_earlier(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    first_session = await new_session(client, headers)
    fake_classifier.results = [durable(), route("memory_query", ["career"])]
    fake_llm.json_replies = [extraction(extracted(text=f"Career goal: plans to switch jobs in {NEXT_YEAR}."))]
    await ask(client, headers, first_session, SWITCH_JOBS)
    goal_id = (await memory_nodes(headers))[0]["id"]

    second_session = await new_session(client, headers)  # a brand-new conversation
    body = await ask(client, headers, second_session, "What do you remember about my career goals?")

    assert body["context_used"] == ["user_profile", "zodiac", f"goal:{goal_id}"]
    assert "history" not in body["context_used"]  # nothing carried over from the first session
    prompt = prompt_text(fake_llm)
    assert f"- goal (career): Career goal: plans to switch jobs in {NEXT_YEAR}. (stated today)" in prompt
    assert SWITCH_JOBS not in prompt  # the old conversation itself is not sent, only the memory


async def test_scenario_7_correcting_a_memory_supersedes_the_old_one(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    old_id = await add_memory(headers, "Career goal: plans to switch jobs in 2027.", attributes={"target_year": 2027})
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(), route("general", ["career"])]
    fake_llm.json_replies = [
        extraction(
            extracted(
                action="update",
                target_id=old_id,
                text="Career goal: plans to switch jobs in 2028.",
                attributes={"target_year": 2028},
            )
        )
    ]

    body = await ask(client, headers, session_id, "Actually, I'll switch jobs in 2028, not 2027.")

    old, new = await memory_nodes(headers)
    assert old["id"] == old_id
    assert old["status"] == "superseded"
    assert old["superseded_by"] == new["id"]
    assert new["status"] == "active"
    assert new["text"] == "Career goal: plans to switch jobs in 2028."
    assert json.loads(new["attributes"]) == {"target_year": 2028}
    assert new["label"] == "Goal" and new["area"] == "career"
    # The audit row says "updated" and points at the NEW node.
    event = (await events_for(body["message_id"]))[0]
    assert (event.action, event.memory_id) == ("updated", new["id"])

    # From now on only the corrected memory is ever retrieved.
    later = await ask(client, headers, session_id, "What should I focus on for my career?")
    assert [label for label in later["context_used"] if ":" in label] == [f"goal:{new['id']}"]
    assert "2027" not in prompt_text(fake_llm).split("[MEMORY]")[1].split("[HISTORY]")[0]


async def test_scenario_7_correcting_the_profile_updates_the_user_and_the_zodiac(client, fake_llm, fake_classifier):
    headers = await onboard(client)  # born 1995-08-15: Leo
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(["general"])]
    fake_llm.json_replies = [extraction(profile_correction("dob", "1995-03-25"))]

    body = await ask(client, headers, session_id, "Actually I was born on 25 March 1995, not in August.")

    me = (await client.get("/users/me", headers=headers)).json()
    assert me["profile"]["dob"] == "1995-03-25"
    assert me["profile"]["zodiac"]["name"] == "Aries"  # the link moved from Leo
    assert me["profile"]["profile_updated_via"] == "chat"
    assert me["profile"]["name"] == "Rahul"  # untouched fields stay
    records, _, _ = await app.state.neo4j.execute_query(
        "MATCH (:User {id: $id})-[:HAS_ZODIAC]->(z) RETURN z.name AS name", id=user_id_of(headers)
    )
    assert [r["name"] for r in records] == ["Aries"]  # exactly one zodiac link
    # A profile correction is not a memory node...
    assert await memory_nodes(headers) == []
    # ...but it is recorded and shown to the user.
    assert await updates(client, headers, body["message_id"]) == {
        "status": "done",
        "updates": [
            {
                "action": "profile_corrected",
                "kind": "profile_correction",
                "title": "Date of birth updated",
                "life_area": "general",
                "memory_id": None,
            }
        ],
    }


# =============================================================================
# The gate
# =============================================================================


async def test_gate_skip_never_calls_the_extraction_llm(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [route("general", ["career"], durable=0.2)]

    body = await ask(client, headers, session_id, "What should I focus on for my career?")

    assert fake_llm.json_calls == []
    assert await memory_nodes(headers) == []
    assert await updates(client, headers, body["message_id"]) == {"status": "skipped", "updates": []}


async def test_a_message_with_nothing_worth_storing_ends_as_done_with_no_updates(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [extraction()]

    body = await ask(client, headers, session_id, "I had a long day.")

    assert await memory_nodes(headers) == []
    assert await updates(client, headers, body["message_id"]) == {"status": "done", "updates": []}


# =============================================================================
# Applying extracted items
# =============================================================================


async def test_each_kind_gets_its_own_label_and_relationship(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [
        extraction(
            extracted("Wants to start a business.", kind="goal", life_area="career", title="Start a business"),
            extracted("Interested in entrepreneurship.", kind="interest", life_area="career", title="Entrepreneurship"),
            extracted("Prefers short, direct answers.", kind="preference", life_area="general", title="Short answers"),
            extracted("Got married in 2024.", kind="memory", life_area="relationships", title="Married"),
        )
    ]

    body = await ask(client, headers, session_id, "A lot about me.")

    nodes = await memory_nodes(headers)
    assert sorted((n["label"], n["relationship"], n["area"]) for n in nodes) == [
        ("Goal", "HAS_GOAL", "career"),
        ("Interest", "INTERESTED_IN", "career"),
        ("Memory", "HAS_MEMORY", "relationships"),
        ("Preference", "PREFERS", "general"),
    ]
    assert len((await updates(client, headers, body["message_id"]))["updates"]) == 4


async def test_skip_items_store_nothing(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    existing = await add_memory(headers, "Career goal: plans to switch jobs in 2027.")
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [extraction(extracted(action="skip", target_id=existing))]

    body = await ask(client, headers, session_id, "As I said, I plan to switch jobs in 2027.")

    assert [n["id"] for n in await memory_nodes(headers)] == [existing]  # no duplicate
    assert await updates(client, headers, body["message_id"]) == {"status": "done", "updates": []}


async def test_invalid_items_are_dropped_and_valid_ones_still_applied(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [
        extraction(
            extracted("Loves astronomy.", kind="interest", life_area="astronomy"),  # invented life area
            extracted("Something.", action="update", target_id="no-such-memory"),  # unknown target
            extracted("   ", title="Empty"),  # empty text
            extracted("Too sure.", confidence=1.7),  # out of range
            profile_correction("dob", "2999-01-01"),  # in the future
            profile_correction("dob", "the fifth of May"),  # not a date
            profile_correction("birth_time", "tea time"),  # not a time
            profile_correction("name", "   "),  # empty
            extracted("Wants to learn Spanish.", kind="goal", life_area="education", title="Learn Spanish"),  # valid
        )
    ]

    body = await ask(client, headers, session_id, "Many things.")

    nodes = await memory_nodes(headers)
    assert [(n["text"], n["area"]) for n in nodes] == [("Wants to learn Spanish.", "education")]
    assert (await client.get("/users/me", headers=headers)).json()["profile"]["dob"] == "1995-08-15"
    result = await updates(client, headers, body["message_id"])
    assert result["status"] == "done"
    assert [u["title"] for u in result["updates"]] == ["Learn Spanish"]


async def test_update_cannot_touch_another_users_memory(client, fake_llm, fake_classifier):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com")
    rahul_memory = await add_memory(rahul, "Career goal: plans to switch jobs in 2027.")
    session_id = await new_session(client, priya)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [extraction(extracted("Hijacked.", action="update", target_id=rahul_memory))]

    await ask(client, priya, session_id, "Change that memory.")

    rahul_nodes = await memory_nodes(rahul)
    assert [(n["id"], n["status"]) for n in rahul_nodes] == [(rahul_memory, "active")]
    assert await memory_nodes(priya) == []


async def test_birth_time_correction_marks_the_time_as_known(client, fake_llm, fake_classifier):
    headers = await onboard(client, birth_time_known=False)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(["general"])]
    fake_llm.json_replies = [extraction(profile_correction("birth_time", "06:45"))]

    body = await ask(client, headers, session_id, "I found out I was born at 6:45 in the morning.")

    profile = (await client.get("/users/me", headers=headers)).json()["profile"]
    assert profile["birth_time"] == "06:45:00"
    assert profile["birth_time_known"] is True
    assert (await updates(client, headers, body["message_id"]))["updates"][0]["title"] == "Birth time updated"


async def test_profile_given_in_chat_completes_the_profile(client, fake_llm, fake_classifier):
    """The assignment's first example: profile facts and a goal in one message, no onboarding form."""
    headers = await signup(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(), route("general", ["career"])]
    fake_llm.json_replies = [
        extraction(
            profile_correction("name", "Rahul"),
            profile_correction("dob", "1995-08-15"),
            profile_correction("birth_place", "Delhi"),
            extracted(text=f"Career goal: plans to switch jobs in {NEXT_YEAR}.", attributes={"target_year": NEXT_YEAR}),
        )
    ]

    first = await ask(
        client, headers, session_id,
        "My name is Rahul. I was born on 15 August 1995 in Delhi. I'm planning to switch jobs next year.",
    )

    me = (await client.get("/users/me", headers=headers)).json()
    assert me["profile_complete"] is True
    assert me["profile"]["name"] == "Rahul"
    assert me["profile"]["birth_place"] == "Delhi"
    assert me["profile"]["birth_time_known"] is False
    assert me["profile"]["zodiac"]["name"] == "Leo"
    assert me["profile"]["profile_updated_via"] == "chat"
    assert [u["action"] for u in (await updates(client, headers, first["message_id"]))["updates"]] == [
        "profile_corrected", "profile_corrected", "profile_corrected", "created",
    ]
    assert "has not completed their birth details" in prompt_text(fake_llm)  # true at the time of turn 1

    # Later in the same conversation: personalised, and no more nudge.
    goal_id = (await memory_nodes(headers))[0]["id"]
    second = await ask(client, headers, session_id, "What should I focus on for my career?")
    assert second["context_used"] == ["user_profile", "zodiac", "history", f"goal:{goal_id}"]
    assert "has not completed their birth details" not in prompt_text(fake_llm)
    assert "Sun sign: Leo (Fire)" in prompt_text(fake_llm)


async def test_partial_profile_from_chat_does_not_complete_it(client, fake_llm, fake_classifier):
    headers = await signup(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(["general"])]
    fake_llm.json_replies = [extraction(profile_correction("name", "Rahul"))]

    await ask(client, headers, session_id, "My name is Rahul.")

    me = (await client.get("/users/me", headers=headers)).json()
    assert me["profile"]["name"] == "Rahul"
    assert me["profile_complete"] is False  # dob and birth place are still missing


# =============================================================================
# Failures: memory writes are best-effort and never affect the chat reply
# =============================================================================


async def test_extraction_failure_marks_the_message_failed_but_chat_is_fine(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = []  # FakeLLM raises LLMError for the extraction call

    body = await ask(client, headers, session_id, SWITCH_JOBS)

    assert body["response"] == "FAKE REPLY"
    assert await memory_nodes(headers) == []
    assert await updates(client, headers, body["message_id"]) == {"status": "failed", "updates": []}


async def test_neo4j_failure_during_the_task_marks_the_message_failed(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [extraction(extracted())]

    # Neo4j works for the chat turn but is gone when the background task runs.
    original_run = MemoryTask.run

    async def run_with_neo4j_down(self, job):
        self.memories.driver = BrokenNeo4jDriver()
        self.profiles.driver = BrokenNeo4jDriver()
        await original_run(self, job)

    MemoryTask.run = run_with_neo4j_down
    try:
        body = await ask(client, headers, session_id, SWITCH_JOBS)
    finally:
        MemoryTask.run = original_run

    assert body["response"] == "FAKE REPLY"
    assert body["context_used"] == ["user_profile", "zodiac"]  # the chat turn itself was normal
    assert await updates(client, headers, body["message_id"]) == {"status": "failed", "updates": []}


async def test_postgres_failure_after_neo4j_success_is_logged_as_an_inconsistency(
    client, fake_llm, fake_classifier, monkeypatch, caplog
):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable()]
    fake_llm.json_replies = [extraction(extracted())]

    async def failing_record_done(self, message_id, events):
        raise ConnectionError("Postgres went away")

    monkeypatch.setattr(MemoryEventRepository, "record_done", failing_record_done)

    body = await ask(client, headers, session_id, SWITCH_JOBS)

    # The memory exists in the brain; only its audit row is missing. That is acceptable.
    nodes = await memory_nodes(headers)
    assert len(nodes) == 1
    assert await events_for(body["message_id"]) == []
    assert await status_of(body["message_id"]) == "failed"
    assert "INCONSISTENCY" in caplog.text
    assert nodes[0]["id"] in caplog.text
    assert body["response"] == "FAKE REPLY"


# =============================================================================
# Memory polling: GET /messages/{id}/memory-updates
# =============================================================================


async def test_polling_shows_pending_while_the_task_has_not_finished(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    body = await ask(client, headers, session_id, "Hello")
    async with app.state.session_factory() as db:
        await MemoryEventRepository(db).set_status(uuid.UUID(body["message_id"]), "pending")

    assert await updates(client, headers, body["message_id"]) == {"status": "pending", "updates": []}


async def test_polling_is_limited_to_the_users_own_user_messages(client, fake_llm, fake_classifier):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com")
    session_id = await new_session(client, rahul)
    body = await ask(client, rahul, session_id, "Hello")
    async with app.state.session_factory() as db:
        assistant = (
            await db.execute(select(MessageRow).where(MessageRow.role == "assistant"))
        ).scalar_one()

    other_user = await client.get(f"/messages/{body['message_id']}/memory-updates", headers=priya)
    assistant_message = await client.get(f"/messages/{assistant.id}/memory-updates", headers=rahul)
    missing = await client.get(f"/messages/{uuid.uuid4()}/memory-updates", headers=rahul)
    malformed = await client.get("/messages/msg-789/memory-updates", headers=rahul)
    no_token = await client.get(f"/messages/{body['message_id']}/memory-updates")

    assert other_user.status_code == 404
    assert assistant_message.status_code == 404
    assert missing.status_code == 404
    assert malformed.status_code == 422
    assert no_token.status_code == 401


# =============================================================================
# Memory page: GET /users/me/memory and DELETE /users/me/memory/{id}
# =============================================================================


async def test_memory_page_groups_active_memories_by_life_area(client, fake_llm):
    headers = await onboard(client)
    goal = await add_memory(headers, "Career goal: plans to switch jobs in 2027.", life_area="career", days_old=5, title="Switch jobs", attributes={"target_year": 2027})
    newer = await add_memory(headers, "Career: wants to lead a team.", life_area="career", days_old=1)
    health = await add_memory(headers, "Health: runs every morning.", kind="interest", life_area="health")
    await add_memory(headers, "An outdated goal.", life_area="career", status="superseded")

    response = await client.get("/users/me/memory", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body["memories"]) == {"career", "health"}
    assert [m["id"] for m in body["memories"]["career"]] == [newer, goal]  # newest first, superseded hidden
    assert [m["id"] for m in body["memories"]["health"]] == [health]
    first_goal = body["memories"]["career"][1]
    assert first_goal["kind"] == "goal"
    assert first_goal["title"] == "Switch jobs"
    assert first_goal["attributes"] == {"target_year": 2027}
    assert set(first_goal) == {"id", "kind", "title", "text", "life_area", "attributes", "created_at"}
    # The profile summary comes with it.
    assert body["profile"]["name"] == "Rahul"
    assert body["profile"]["zodiac"]["name"] == "Leo"


async def test_memory_page_for_a_new_user_is_empty(client):
    headers = await signup(client)

    body = (await client.get("/users/me/memory", headers=headers)).json()

    assert body == {"profile": None, "memories": {}}


async def test_users_only_see_their_own_memories_on_the_memory_page(client):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com")
    await add_memory(rahul, "Career goal: plans to switch jobs in 2027.")

    assert (await client.get("/users/me/memory", headers=priya)).json()["memories"] == {}


async def test_deleting_a_memory_removes_it_everywhere_but_keeps_the_audit_log(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(), route("general", ["career"])]
    fake_llm.json_replies = [extraction(extracted())]
    created = await ask(client, headers, session_id, SWITCH_JOBS)
    goal_id = (await memory_nodes(headers))[0]["id"]

    response = await client.delete(f"/users/me/memory/{goal_id}", headers=headers)

    assert response.status_code == 204
    assert await memory_nodes(headers) == []
    assert (await client.get("/users/me/memory", headers=headers)).json()["memories"] == {}
    # It is no longer used in answers.
    later = await ask(client, headers, session_id, "What should I focus on for my career?")
    assert f"goal:{goal_id}" not in later["context_used"]
    # Past memory_events rows stay as history.
    assert len(await events_for(created["message_id"])) == 1
    # Deleting it again is a 404.
    assert (await client.delete(f"/users/me/memory/{goal_id}", headers=headers)).status_code == 404


async def test_a_user_cannot_delete_another_users_memory(client):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com")
    memory_id = await add_memory(rahul, "Career goal: plans to switch jobs in 2027.")

    response = await client.delete(f"/users/me/memory/{memory_id}", headers=priya)

    assert response.status_code == 404
    assert [n["id"] for n in await memory_nodes(rahul)] == [memory_id]


async def test_deleting_a_memory_does_not_revive_the_one_it_superseded(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    old_id = await add_memory(headers, "Career goal: plans to switch jobs in 2027.")
    session_id = await new_session(client, headers)
    fake_classifier.results = [durable(), route("general", ["career"])]
    fake_llm.json_replies = [extraction(extracted("Career goal: plans to switch jobs in 2028.", action="update", target_id=old_id))]
    await ask(client, headers, session_id, "Actually 2028.")
    new_id = next(n["id"] for n in await memory_nodes(headers) if n["status"] == "active")

    await client.delete(f"/users/me/memory/{new_id}", headers=headers)

    remaining = await memory_nodes(headers)
    assert [(n["id"], n["status"]) for n in remaining] == [(old_id, "superseded")]
    later = await ask(client, headers, session_id, "Career advice?")
    assert [label for label in later["context_used"] if ":" in label] == []


async def test_memory_endpoints_require_a_token(client):
    assert (await client.get("/users/me/memory")).status_code == 401
    assert (await client.delete(f"/users/me/memory/{uuid.uuid4()}")).status_code == 401
