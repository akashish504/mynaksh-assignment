"""Rate limiting on POST /chat: 20 requests per minute, counted per user."""

from tests.conftest import new_session, onboard


async def send(client, headers, session_id):
    return await client.post("/chat", json={"session_id": session_id, "message": "Hello"}, headers=headers)


async def test_the_21st_chat_request_in_a_minute_is_rejected(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)

    statuses = [(await send(client, headers, session_id)).status_code for _ in range(20)]
    blocked = await send(client, headers, session_id)

    assert statuses == [200] * 20
    assert blocked.status_code == 429
    assert "too quickly" in blocked.json()["detail"]
    # The rejected request never reached the pipeline.
    assert len(fake_llm.calls) == 20


async def test_the_limit_is_counted_per_user(client, fake_llm, fake_classifier):
    rahul = await onboard(client, "rahul@example.com")
    priya = await onboard(client, "priya@example.com")
    rahul_session = await new_session(client, rahul)
    priya_session = await new_session(client, priya)
    for _ in range(20):
        await send(client, rahul, rahul_session)

    rahul_blocked = await send(client, rahul, rahul_session)
    priya_allowed = await send(client, priya, priya_session)

    assert rahul_blocked.status_code == 429
    assert priya_allowed.status_code == 200  # Rahul using up his limit does not affect Priya


async def test_only_chat_is_rate_limited(client, fake_llm, fake_classifier):
    headers = await onboard(client)
    session_id = await new_session(client, headers)
    for _ in range(21):
        await send(client, headers, session_id)

    # Other endpoints keep working for a user who hit the chat limit.
    assert (await client.get("/sessions", headers=headers)).status_code == 200
    assert (await client.get("/users/me/memory", headers=headers)).status_code == 200


async def test_a_request_without_a_token_is_still_a_401(client):
    response = await client.post("/chat", json={"session_id": "00000000-0000-0000-0000-000000000000", "message": "Hello"})

    assert response.status_code == 401
