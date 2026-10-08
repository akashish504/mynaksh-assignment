"""Shared Brain schema setup: constraints and seed nodes. Safe to run on every startup."""

from neo4j import AsyncDriver

from app.profile.zodiac_data import ZODIAC_SIGNS

# The fixed, closed list of life areas. It is the retrieval key: the same list is
# used when storing memories and when routing queries. The LLM never adds to it.
LIFE_AREAS = [
    "career",
    "finance",
    "relationships",
    "family",
    "health",
    "education",
    "spirituality",
    "travel",
    "general",
]

# Every label whose nodes are looked up by `id`.
LABELS_WITH_UNIQUE_ID = ["User", "Goal", "Interest", "Preference", "Memory"]


async def setup_schema(driver: AsyncDriver) -> None:
    for label in LABELS_WITH_UNIQUE_ID:
        # Labels cannot be query parameters in Cypher; these come from the fixed list above.
        await driver.execute_query(
            f"CREATE CONSTRAINT {label.lower()}_id_unique IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        )

    # MERGE creates a node only if it does not exist yet, so re-running adds nothing.
    await driver.execute_query(
        "UNWIND $names AS name MERGE (:LifeArea {name: name})",
        names=LIFE_AREAS,
    )
    await driver.execute_query(
        "UNWIND $signs AS sign "
        "MERGE (z:Zodiac {name: sign.name}) "
        "SET z.element = sign.element, z.traits = sign.traits",
        signs=ZODIAC_SIGNS,
    )
