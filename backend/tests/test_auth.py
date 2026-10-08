"""Signup, login, tokens, the two-store signup compensation, and Postgres-down behavior."""

from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.config import get_settings
from app.db.models import UserRow
from app.main import app
from tests.conftest import signup

CREDENTIALS = {"email": "rahul@example.com", "password": "correct-horse"}


async def postgres_users() -> list[UserRow]:
    async with app.state.session_factory() as db:
        return list((await db.execute(select(UserRow))).scalars())


async def neo4j_user_ids() -> list[str]:
    records, _, _ = await app.state.neo4j.execute_query("MATCH (u:User) RETURN u.id AS id")
    return [record["id"] for record in records]


# --- signup ---


async def test_signup_creates_the_user_in_both_stores_with_one_id(client):
    response = await client.post("/auth/signup", json=CREDENTIALS)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["profile_complete"] is False
    assert body["access_token"]

    users = await postgres_users()
    assert len(users) == 1
    assert users[0].email == "rahul@example.com"
    assert users[0].password_hash != CREDENTIALS["password"]  # stored hashed, never in plain text
    assert users[0].profile_complete is False
    # The same id is used in Neo4j.
    assert await neo4j_user_ids() == [str(users[0].id)]


async def test_signup_stores_the_email_lower_cased(client):
    await client.post("/auth/signup", json={"email": "Rahul@Example.com", "password": "correct-horse"})

    assert [user.email for user in await postgres_users()] == ["rahul@example.com"]


async def test_signup_with_an_existing_email_returns_409(client):
    await client.post("/auth/signup", json=CREDENTIALS)

    response = await client.post(
        "/auth/signup", json={"email": "RAHUL@example.com", "password": "another-password"}
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    assert len(await postgres_users()) == 1


async def test_signup_rejects_invalid_input(client):
    bad_email = await client.post("/auth/signup", json={"email": "not-an-email", "password": "correct-horse"})
    short_password = await client.post("/auth/signup", json={"email": "a@example.com", "password": "short"})
    too_long = await client.post("/auth/signup", json={"email": "a@example.com", "password": "x" * 73})

    assert bad_email.status_code == 422
    assert short_password.status_code == 422
    assert too_long.status_code == 422
    assert await postgres_users() == []


async def test_signup_removes_the_postgres_user_when_neo4j_fails(client, neo4j_down):
    """Compensating action: no user may be left in Postgres without a Neo4j node."""
    response = await client.post("/auth/signup", json=CREDENTIALS)

    assert response.status_code == 503
    assert "try again" in response.json()["detail"]
    assert await postgres_users() == []


async def test_signup_can_be_retried_after_a_neo4j_failure(client):
    real_driver = app.state.neo4j

    class BrokenDriver:
        async def execute_query(self, *args, **kwargs):
            raise ConnectionError("Neo4j is unreachable")

    app.state.neo4j = BrokenDriver()
    try:
        failed = await client.post("/auth/signup", json=CREDENTIALS)
    finally:
        app.state.neo4j = real_driver
    retried = await client.post("/auth/signup", json=CREDENTIALS)

    assert failed.status_code == 503
    assert retried.status_code == 201


# --- login ---


async def test_login_returns_a_token_and_the_profile_flag(client):
    await client.post("/auth/signup", json=CREDENTIALS)

    response = await client.post("/auth/login", json={"email": "RAHUL@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["profile_complete"] is False
    # The token works on a protected endpoint.
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert (await client.get("/users/me", headers=headers)).status_code == 200


async def test_login_does_not_need_neo4j(client, neo4j_down):
    # Signup needs Neo4j, so create the Postgres row directly.
    from app.auth.passwords import hash_password
    from app.db import user_repository

    async with app.state.session_factory() as db:
        await user_repository.create(db, "rahul@example.com", hash_password("correct-horse"))

    response = await client.post("/auth/login", json=CREDENTIALS)

    assert response.status_code == 200


async def test_login_with_wrong_password_or_unknown_email_returns_401(client):
    await client.post("/auth/signup", json=CREDENTIALS)

    wrong_password = await client.post("/auth/login", json={**CREDENTIALS, "password": "wrong-password"})
    unknown_email = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "correct-horse"})

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    # Same message for both, so the response does not reveal which emails are registered.
    assert wrong_password.json() == unknown_email.json()


# --- tokens on protected endpoints ---


async def test_protected_endpoint_without_a_token_returns_401(client):
    response = await client.get("/users/me")

    assert response.status_code == 401


async def test_protected_endpoint_with_a_bad_token_returns_401(client):
    response = await client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


async def test_expired_token_returns_401(client):
    await signup(client)
    user = (await postgres_users())[0]
    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


async def test_token_signed_with_another_secret_returns_401(client):
    await signup(client)
    user = (await postgres_users())[0]
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "some-other-secret-that-is-long-enough-to-use",
        algorithm="HS256",
    )

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


async def test_token_for_a_deleted_user_returns_401(client):
    headers = await signup(client)
    async with app.state.session_factory() as db:
        user = (await db.execute(select(UserRow))).scalar_one()
        await db.delete(user)
        await db.commit()

    response = await client.get("/users/me", headers=headers)

    assert response.status_code == 401


# --- Postgres down ---


async def test_auth_returns_503_when_postgres_is_down(client, postgres_down):
    signup_response = await client.post("/auth/signup", json=CREDENTIALS)
    login_response = await client.post("/auth/login", json=CREDENTIALS)

    assert signup_response.status_code == 503
    assert login_response.status_code == 503
    assert "temporarily unavailable" in login_response.json()["detail"]
    # No partial write to Neo4j.
    assert await neo4j_user_ids() == []
