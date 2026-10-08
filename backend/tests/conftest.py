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

from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Run the Alembic migrations before the suite. This also tests the migrations."""
    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_config, "head")


@pytest_asyncio.fixture
async def client():
    # httpx does not run FastAPI's startup/shutdown by itself, so it is done here.
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
