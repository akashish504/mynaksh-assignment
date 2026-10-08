"""Shared test setup.

Tests always run against the local Docker databases (or CI service containers).
The environment variables are overwritten here, before the app is imported, so a
real .env file can never point the test suite at Neon or AuraDB.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://mynaksh:mynaksh@localhost:5433/mynaksh"
)
os.environ["DATABASE_URL_DIRECT"] = os.environ["DATABASE_URL"]
os.environ["NEO4J_URI"] = os.environ.get("TEST_NEO4J_URI", "bolt://localhost:7687")
os.environ["NEO4J_USER"] = os.environ.get("TEST_NEO4J_USER", "neo4j")
os.environ["NEO4J_PASSWORD"] = os.environ.get("TEST_NEO4J_PASSWORD", "mynaksh-dev-password")
os.environ["JWT_SECRET"] = "test-only-secret-for-local-throwaway-databases"
# No real LLM, classifier or tracing calls from tests, whatever .env says.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["TYPESAFE_API_KEY"] = "test-key-never-sent-anywhere"
os.environ["PRIMARY_MODEL"] = "test/primary-model"
os.environ["FALLBACK_MODEL"] = ""

from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Run the Alembic migrations before the suite. This also tests the migrations."""
    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_config, "head")


async def wipe_databases() -> None:
    """Remove all user data so every test starts from the same empty state.

    The seeded Zodiac and LifeArea nodes are kept.
    """
    async with app.state.engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE memory_events, messages, sessions, users RESTART IDENTITY CASCADE")
        )
    await app.state.neo4j.execute_query(
        "MATCH (n) WHERE NOT n:Zodiac AND NOT n:LifeArea DETACH DELETE n"
    )


@pytest_asyncio.fixture
async def client():
    # httpx does not run FastAPI's startup/shutdown by itself, so it is done here.
    async with app.router.lifespan_context(app):
        await wipe_databases()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


class BrokenNeo4jDriver:
    """Stands in for the Neo4j driver when a test needs Neo4j to be down."""

    async def execute_query(self, *args, **kwargs):
        from neo4j.exceptions import ServiceUnavailable

        raise ServiceUnavailable("Neo4j is unreachable")


@pytest.fixture
def neo4j_down(client):
    """Make Neo4j look unreachable for the rest of the test."""
    real_driver = app.state.neo4j
    app.state.neo4j = BrokenNeo4jDriver()
    yield
    app.state.neo4j = real_driver


@pytest.fixture
def postgres_down(client):
    """Make Postgres look unreachable for the rest of the test."""
    from app.db.engine import create_engine, create_session_factory

    real_factory = app.state.session_factory
    # Nothing listens on this port, so every query fails to connect.
    dead_engine = create_engine("postgresql://nobody:nothing@localhost:1/none")
    app.state.session_factory = create_session_factory(dead_engine)
    yield
    app.state.session_factory = real_factory


async def signup(client: AsyncClient, email: str = "rahul@example.com") -> dict:
    """Sign a user up and return the Authorization headers for them."""
    response = await client.post("/auth/signup", json={"email": email, "password": "correct-horse"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


VALID_PROFILE = {
    "name": "Rahul",
    "dob": "1995-08-15",
    "birth_time": "14:30:00",
    "birth_time_known": True,
    "birth_place": "Delhi",
}


# --- Chat test helpers --------------------------------------------------------

import uuid
from datetime import datetime, timedelta, timezone

from app.auth.tokens import read_user_id
from app.brain.memory_repository import MemoryRepository
from app.classifier.base import RouteResult
from app.classifier.fake import FakeClassifier
from app.llm.fake import FakeLLM
from app.models.memory import MemoryNode


def route(intent="general", areas=("general",), durable=0.1, confidence=0.95) -> RouteResult:
    """A scripted routing decision for FakeClassifier."""
    return RouteResult(
        intent=intent,
        intent_confidence=confidence,
        areas=list(areas),
        has_durable_fact=durable,
        source="jev",
    )


@pytest.fixture
def fake_llm(client):
    """Replace the real LLM with FakeLLM for the test. Nothing is sent to a provider."""
    real_llm = app.state.llm
    app.state.llm = FakeLLM()
    yield app.state.llm
    app.state.llm = real_llm


@pytest.fixture
def fake_classifier(client):
    """Replace the real classifier with a scripted one. Set `.results` in the test."""
    real_classifier = app.state.classifier
    app.state.classifier = FakeClassifier(route())
    yield app.state.classifier
    app.state.classifier = real_classifier


def user_id_of(headers: dict) -> str:
    token = headers["Authorization"].removeprefix("Bearer ")
    return str(read_user_id(token))


async def onboard(client: AsyncClient, email: str = "rahul@example.com", **profile_changes) -> dict:
    """Sign up and complete the onboarding form. Returns the Authorization headers."""
    headers = await signup(client, email)
    response = await client.put(
        "/users/me/profile", json={**VALID_PROFILE, **profile_changes}, headers=headers
    )
    assert response.status_code == 200, response.text
    return headers


async def new_session(client: AsyncClient, headers: dict) -> str:
    response = await client.post("/sessions", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def add_memory(
    headers: dict,
    text: str,
    kind: str = "goal",
    life_area: str = "career",
    confidence: float = 0.9,
    importance: float = 0.8,
    days_old: int = 0,
    status: str = "active",
    title: str = "A memory",
    attributes: dict | None = None,
) -> str:
    """Put a memory node straight into Neo4j for the user and return its id."""
    when = datetime.now(timezone.utc) - timedelta(days=days_old)
    memory = MemoryNode(
        id=str(uuid.uuid4()),
        kind=kind,
        title=title,
        text=text,
        life_area=life_area,
        attributes=attributes or {},
        confidence=confidence,
        importance=importance,
        status=status,
        created_at=when,
        updated_at=when,
    )
    await MemoryRepository(app.state.neo4j).create(user_id_of(headers), memory)
    return memory.id


async def ask(client: AsyncClient, headers: dict, session_id: str, message: str) -> dict:
    response = await client.post(
        "/chat", json={"session_id": session_id, "message": message}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def prompt_text(llm: FakeLLM, call: int = -1) -> str:
    """Everything that was sent to the LLM in one call, as a single string."""
    return "\n\n".join(message["content"] for message in llm.calls[call])
