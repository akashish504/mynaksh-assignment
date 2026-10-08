"""Phase 1 checks: URL handling, the Postgres migration, and Neo4j schema setup."""

from sqlalchemy import text

from app.brain.schema import LABELS_WITH_UNIQUE_ID, LIFE_AREAS, setup_schema
from app.db.engine import asyncpg_url_and_args
from app.main import app


def test_neon_style_url_is_converted_for_asyncpg():
    url, connect_args = asyncpg_url_and_args(
        "postgresql://someone:secret@db.example.com/appdb?sslmode=require&channel_binding=require"
    )

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "db.example.com"
    assert url.database == "appdb"
    assert dict(url.query) == {}
    assert connect_args["ssl"] == "require"
    assert connect_args["statement_cache_size"] == 0
    assert connect_args["prepared_statement_cache_size"] == 0


def test_local_url_without_sslmode_does_not_force_ssl():
    url, connect_args = asyncpg_url_and_args("postgresql://someone:secret@localhost:5433/appdb")

    assert url.drivername == "postgresql+asyncpg"
    assert "ssl" not in connect_args


async def test_migration_creates_the_four_tables(client):
    async with app.state.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        tables = {row[0] for row in result}

    assert {"users", "sessions", "messages", "memory_events"} <= tables


async def test_neo4j_seed_is_complete_and_idempotent(client):
    driver = app.state.neo4j
    # Startup already ran setup_schema once; a second run must not add anything.
    await setup_schema(driver)

    life_areas, _, _ = await driver.execute_query("MATCH (a:LifeArea) RETURN a.name AS name")
    zodiac_signs, _, _ = await driver.execute_query(
        "MATCH (z:Zodiac) RETURN z.name AS name, z.element AS element, z.traits AS traits"
    )

    assert sorted(record["name"] for record in life_areas) == sorted(LIFE_AREAS)
    assert len(zodiac_signs) == 12
    leo = next(record for record in zodiac_signs if record["name"] == "Leo")
    assert leo["element"] == "Fire"
    assert len(leo["traits"]) > 0


async def test_neo4j_unique_id_constraints_exist(client):
    records, _, _ = await app.state.neo4j.execute_query(
        "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
        "WHERE type = 'UNIQUENESS' AND properties = ['id'] "
        "RETURN labelsOrTypes[0] AS label"
    )

    assert {record["label"] for record in records} >= set(LABELS_WITH_UNIQUE_ID)
