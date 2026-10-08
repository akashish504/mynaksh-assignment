"""Neo4j access for the User node, its profile properties and its zodiac link."""

from datetime import date, time

from fastapi import Depends
from neo4j import AsyncDriver

from app.brain.driver import get_driver
from app.models.profile import Profile, Zodiac

MERGE_USER = """
MERGE (u:User {id: $user_id})
ON CREATE SET u.language = 'en', u.created_at = datetime(), u.updated_at = datetime()
"""

# One query, so it is one transaction: either everything is written or nothing is.
# Running it again with the same values changes nothing, which makes retries safe.
SAVE_PROFILE = """
MERGE (u:User {id: $user_id})
ON CREATE SET u.created_at = datetime()
SET u.name = $name,
    u.dob = $dob,
    u.birth_time = $birth_time,
    u.birth_time_known = $birth_time_known,
    u.birth_place = $birth_place,
    u.language = $language,
    u.profile_updated_via = $updated_via,
    u.updated_at = datetime()
// Remove the old zodiac link (if any), then create the new one.
WITH u
OPTIONAL MATCH (u)-[old:HAS_ZODIAC]->(:Zodiac)
DELETE old
WITH DISTINCT u
MERGE (z:Zodiac {name: $sun_sign})
MERGE (u)-[:HAS_ZODIAC]->(z)
"""

# `SET u += $changes` updates only the properties named in the map.
UPDATE_FROM_CHAT = """
MATCH (u:User {id: $user_id})
SET u += $changes, u.profile_updated_via = 'chat', u.updated_at = datetime()
"""

MOVE_ZODIAC_LINK = """
MATCH (u:User {id: $user_id})
OPTIONAL MATCH (u)-[old:HAS_ZODIAC]->(:Zodiac)
DELETE old
WITH DISTINCT u
MERGE (z:Zodiac {name: $sun_sign})
MERGE (u)-[:HAS_ZODIAC]->(z)
"""

GET_PROFILE = """
MATCH (u:User {id: $user_id})
OPTIONAL MATCH (u)-[:HAS_ZODIAC]->(z:Zodiac)
RETURN u, z
"""


class ProfileRepository:
    """All Cypher that reads or writes a user's profile in the Shared Brain."""

    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def merge_user(self, user_id: str) -> None:
        """Create the User node for a new signup. Safe to repeat."""
        await self.driver.execute_query(MERGE_USER, user_id=user_id)

    async def save_profile(
        self,
        user_id: str,
        name: str,
        dob: date,
        birth_time: time | None,
        birth_time_known: bool,
        birth_place: str,
        language: str,
        sun_sign: str,
        updated_via: str,
    ) -> None:
        """Write the profile and point the single HAS_ZODIAC relationship at `sun_sign`."""
        await self.driver.execute_query(
            SAVE_PROFILE,
            user_id=user_id,
            name=name,
            dob=dob,
            birth_time=birth_time,
            birth_time_known=birth_time_known,
            birth_place=birth_place,
            language=language,
            sun_sign=sun_sign,
            updated_via=updated_via,
        )

    async def update_from_chat(self, user_id: str, changes: dict, sun_sign: str | None) -> None:
        """Apply a profile correction the user made in conversation.

        `sun_sign` is given only when the date of birth changed, to move the zodiac link.
        """
        await self.driver.execute_query(UPDATE_FROM_CHAT, user_id=user_id, changes=changes)
        if sun_sign is not None:
            await self.driver.execute_query(MOVE_ZODIAC_LINK, user_id=user_id, sun_sign=sun_sign)

    async def get_profile(self, user_id: str) -> Profile | None:
        """Return the profile with its zodiac, or None if nothing has been filled in yet."""
        records, _, _ = await self.driver.execute_query(GET_PROFILE, user_id=user_id)
        if not records:
            return None

        user = records[0]["u"]
        zodiac = records[0]["z"]
        if user.get("name") is None and user.get("dob") is None and user.get("birth_place") is None:
            return None

        dob = user.get("dob")
        birth_time = user.get("birth_time")
        return Profile(
            name=user.get("name"),
            # Neo4j returns its own date/time types; to_native() converts them to Python's.
            dob=dob.to_native() if dob is not None else None,
            birth_time=birth_time.to_native() if birth_time is not None else None,
            birth_time_known=user.get("birth_time_known") or False,
            birth_place=user.get("birth_place"),
            language=user.get("language") or "en",
            profile_updated_via=user.get("profile_updated_via"),
            zodiac=Zodiac(
                name=zodiac["name"],
                element=zodiac.get("element"),
                traits=zodiac.get("traits") or [],
            )
            if zodiac is not None
            else None,
        )


def get_profile_repository(driver: AsyncDriver = Depends(get_driver)) -> ProfileRepository:
    """FastAPI dependency: a ProfileRepository using the shared Neo4j driver."""
    return ProfileRepository(driver)
