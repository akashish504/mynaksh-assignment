"""Neo4j access for the memory nodes: Goal, Interest, Preference and Memory."""

import json

from fastapi import Depends
from neo4j import AsyncDriver

from app.brain.driver import get_driver
from app.models.memory import MemoryNode

# Each kind of memory has its own node label and its own relationship from the User.
KIND_TO_LABEL = {
    "goal": "Goal",
    "interest": "Interest",
    "preference": "Preference",
    "memory": "Memory",
}
KIND_TO_RELATIONSHIP = {
    "goal": "HAS_GOAL",
    "interest": "INTERESTED_IN",
    "preference": "PREFERS",
    "memory": "HAS_MEMORY",
}

# Matches a user's memory nodes of every kind.
USER_MEMORIES = "(u:User {id: $user_id})-[:HAS_GOAL|INTERESTED_IN|PREFERS|HAS_MEMORY]->(m)"

# The life area is reached by following the ABOUT relationship: this is the retrieval key.
GET_ACTIVE_BY_AREAS = f"""
MATCH {USER_MEMORIES}-[:ABOUT]->(area:LifeArea)
WHERE m.status = 'active' AND area.name IN $areas
RETURN m
"""

GET_ACTIVE_ALL = f"""
MATCH {USER_MEMORIES}
WHERE m.status = 'active'
RETURN m
"""

GET_ACTIVE_BY_IDS = f"""
MATCH {USER_MEMORIES}
WHERE m.status = 'active' AND m.id IN $ids
RETURN m
"""


def create_query(kind: str) -> str:
    # Labels and relationship types cannot be query parameters in Cypher, so they are
    # put into the text here. They come only from the two fixed dictionaries above.
    label = KIND_TO_LABEL[kind]
    relationship = KIND_TO_RELATIONSHIP[kind]
    return f"""
    MATCH (u:User {{id: $user_id}})
    MATCH (area:LifeArea {{name: $life_area}})
    CREATE (m:{label} $properties)
    CREATE (u)-[:{relationship}]->(m)
    CREATE (m)-[:ABOUT]->(area)
    """


def to_memory_node(node) -> MemoryNode:
    properties = dict(node)
    # Neo4j properties cannot hold a map, so `attributes` is stored as a JSON string.
    properties["attributes"] = json.loads(properties.get("attributes") or "{}")
    # Neo4j returns its own DateTime type; to_native() converts it to Python's datetime.
    properties["created_at"] = properties["created_at"].to_native()
    properties["updated_at"] = properties["updated_at"].to_native()
    return MemoryNode(**properties)


class MemoryRepository:
    """All Cypher that reads or writes a user's memories in the Shared Brain.

    Every query starts from the user's own node, so one user can never reach
    another user's memories.
    """

    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def create(self, user_id: str, memory: MemoryNode) -> None:
        properties = memory.model_dump()
        properties["attributes"] = json.dumps(memory.attributes)
        await self.driver.execute_query(
            create_query(memory.kind),
            user_id=user_id,
            life_area=memory.life_area,
            properties=properties,
        )

    async def get_active_by_areas(self, user_id: str, areas: list[str]) -> list[MemoryNode]:
        records, _, _ = await self.driver.execute_query(
            GET_ACTIVE_BY_AREAS, user_id=user_id, areas=areas
        )
        return [to_memory_node(record["m"]) for record in records]

    async def get_active_all(self, user_id: str) -> list[MemoryNode]:
        records, _, _ = await self.driver.execute_query(GET_ACTIVE_ALL, user_id=user_id)
        return [to_memory_node(record["m"]) for record in records]

    async def get_active_by_ids(self, user_id: str, ids: list[str]) -> list[MemoryNode]:
        """Fetch specific memories, in the order the ids were given.

        An id that was deleted or superseded since is simply left out.
        """
        records, _, _ = await self.driver.execute_query(
            GET_ACTIVE_BY_IDS, user_id=user_id, ids=ids
        )
        found = {record["m"]["id"]: to_memory_node(record["m"]) for record in records}
        return [found[memory_id] for memory_id in ids if memory_id in found]


def get_memory_repository(driver: AsyncDriver = Depends(get_driver)) -> MemoryRepository:
    """FastAPI dependency: a MemoryRepository using the shared Neo4j driver."""
    return MemoryRepository(driver)
