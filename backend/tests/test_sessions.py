"""Sessions and messages APIs, and isolation between users."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.message_repository import MessageRepository
from app.db.models import MessageRow, SessionRow, UserRow
from app.main import app
from tests.conftest import signup

START = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


async def add_messages(session_id: str, contents: list[str]) -> None:
    """Insert alternating user/assistant messages, one second apart."""
    async with app.state.session_factory() as db:
        session = await db.get(SessionRow, uuid.UUID(session_id))
        for index, content in enumerate(contents):
            is_user = index % 2 == 0
            db.add(
                MessageRow(
                    session_id=session.id,
                    user_id=session.user_id,
                    role="user" if is_user else "assistant",
                    content=content,
                    type=None if is_user else "answer",
                    context_used=None if is_user else ["history"],
                    memory_status="skipped" if is_user else None,
                    created_at=START + timedelta(seconds=index),
                )
            )
        await db.commit()


async def create_session(client, headers) -> dict:
    response = await client.post("/sessions", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- POST /sessions ---


async def test_create_session_returns_a_new_chat(client):
    headers = await signup(client)

    session = await create_session(client, headers)

    assert session["title"] == "New chat"
    assert uuid.UUID(session["id"])
    assert session["created_at"] and session["updated_at"]


async def test_create_session_belongs_to_the_user_in_the_token(client):
    headers = await signup(client)

    # A user_id in the body is ignored.
    response = await client.post("/sessions", headers=headers, json={"user_id": str(uuid.uuid4())})

    async with app.state.session_factory() as db:
        user = (await db.execute(select(UserRow))).scalar_one()
        session = (await db.execute(select(SessionRow))).scalar_one()
    assert response.status_code == 201
    assert session.user_id == user.id


# --- GET /sessions ---


async def test_list_sessions_is_empty_for_a_new_user(client):
    headers = await signup(client)

    response = await client.get("/sessions", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_list_sessions_shows_the_most_recently_active_first(client):
    headers = await signup(client)
    first = await create_session(client, headers)
    second = await create_session(client, headers)
    third = await create_session(client, headers)

    # Activity in the oldest session moves it to the top.
    async with app.state.session_factory() as db:
        session = await db.get(SessionRow, uuid.UUID(first["id"]))
        session.updated_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        await db.commit()

    response = await client.get("/sessions", headers=headers)

    assert [session["id"] for session in response.json()] == [first["id"], third["id"], second["id"]]


async def test_users_only_see_their_own_sessions(client):
    rahul = await signup(client, "rahul@example.com")
    priya = await signup(client, "priya@example.com")
    rahul_session = await create_session(client, rahul)
    priya_session = await create_session(client, priya)

    rahul_list = (await client.get("/sessions", headers=rahul)).json()
    priya_list = (await client.get("/sessions", headers=priya)).json()

    assert [session["id"] for session in rahul_list] == [rahul_session["id"]]
    assert [session["id"] for session in priya_list] == [priya_session["id"]]


# --- GET /sessions/{id}/messages ---


async def test_messages_are_returned_in_order(client):
    headers = await signup(client)
    session = await create_session(client, headers)
    await add_messages(session["id"], ["Hello", "Hi Rahul", "What about my career?", "Here is my view"])

    response = await client.get(f"/sessions/{session['id']}/messages", headers=headers)

    assert response.status_code == 200
    messages = response.json()
    assert [message["content"] for message in messages] == [
        "Hello",
        "Hi Rahul",
        "What about my career?",
        "Here is my view",
    ]
    assert messages[0]["role"] == "user"
    assert messages[0]["memory_status"] == "skipped"
    assert messages[0]["type"] is None
    assert messages[1]["role"] == "assistant"
    assert messages[1]["type"] == "answer"
    assert messages[1]["context_used"] == ["history"]
    assert messages[1]["memory_status"] is None


async def test_messages_of_a_new_session_are_empty(client):
    headers = await signup(client)
    session = await create_session(client, headers)

    response = await client.get(f"/sessions/{session['id']}/messages", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_another_users_session_returns_404(client):
    rahul = await signup(client, "rahul@example.com")
    priya = await signup(client, "priya@example.com")
    rahul_session = await create_session(client, rahul)
    await add_messages(rahul_session["id"], ["A private message", "A private reply"])

    response = await client.get(f"/sessions/{rahul_session['id']}/messages", headers=priya)

    assert response.status_code == 404
    assert "private" not in response.text


async def test_missing_session_looks_the_same_as_another_users_session(client):
    rahul = await signup(client, "rahul@example.com")
    priya = await signup(client, "priya@example.com")
    rahul_session = await create_session(client, rahul)

    someone_elses = await client.get(f"/sessions/{rahul_session['id']}/messages", headers=priya)
    nonexistent = await client.get(f"/sessions/{uuid.uuid4()}/messages", headers=priya)

    assert nonexistent.status_code == 404
    assert nonexistent.json() == someone_elses.json()


async def test_malformed_session_id_returns_422(client):
    headers = await signup(client)

    response = await client.get("/sessions/not-a-uuid/messages", headers=headers)

    assert response.status_code == 422


async def test_session_endpoints_require_a_token(client):
    assert (await client.post("/sessions")).status_code == 401
    assert (await client.get("/sessions")).status_code == 401
    assert (await client.get(f"/sessions/{uuid.uuid4()}/messages")).status_code == 401


async def test_sessions_return_503_when_postgres_is_down(client):
    headers = await signup(client)
    from app.db.engine import create_engine, create_session_factory

    real_factory = app.state.session_factory
    app.state.session_factory = create_session_factory(
        create_engine("postgresql://nobody:nothing@localhost:1/none")
    )
    try:
        response = await client.get("/sessions", headers=headers)
    finally:
        app.state.session_factory = real_factory

    assert response.status_code == 503


# --- short-term context window ---


async def test_get_recent_returns_only_the_last_messages_oldest_first(client):
    headers = await signup(client)
    session = await create_session(client, headers)
    await add_messages(session["id"], [f"message {number}" for number in range(1, 11)])

    async with app.state.session_factory() as db:
        recent = await MessageRepository(db).get_recent(uuid.UUID(session["id"]), limit=6)

    assert [message.content for message in recent] == [f"message {number}" for number in range(5, 11)]


async def test_get_recent_never_crosses_into_another_session(client):
    headers = await signup(client)
    first = await create_session(client, headers)
    second = await create_session(client, headers)
    await add_messages(first["id"], ["from the first chat", "reply in the first chat"])
    await add_messages(second["id"], ["from the second chat"])

    async with app.state.session_factory() as db:
        recent = await MessageRepository(db).get_recent(uuid.UUID(second["id"]), limit=6)

    assert [message.content for message in recent] == ["from the second chat"]
