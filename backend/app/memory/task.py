"""The background memory task: runs after the reply has been sent.

    extract (LLM)  ->  validate  ->  apply to Neo4j  ->  record in Postgres

Memory writes are best-effort. Whatever goes wrong here is logged and recorded
as memory_status='failed'; it never affects the chat reply the user already has.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from fastapi import Request
from langsmith import traceable
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brain.memory_repository import MemoryRepository
from app.brain.profile_repository import ProfileRepository
from app.brain.schema import LIFE_AREAS
from app.db.memory_event_repository import MemoryEventRepository
from app.db.models import MemoryEventRow
from app.db.user_repository import UserRepository
from app.llm.base import LLMProvider
from app.memory.extractor import MemoryExtractor
from app.memory.schemas import ExtractedItem
from app.models.memory import MemoryNode
from app.profile.sun_sign import sun_sign_for
from app.profile.validation import validate_dob

logger = logging.getLogger(__name__)

PROFILE_FIELD_TITLES = {
    "name": "Name updated",
    "dob": "Date of birth updated",
    "birth_time": "Birth time updated",
    "birth_place": "Birth place updated",
}


@dataclass
class MemoryJob:
    """Everything the task needs, copied out of the request before it ends."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID
    message: str
    # The two messages before this one, as {"role", "content"}.
    recent_messages: list[dict] = field(default_factory=list)


class InvalidItem(Exception):
    """An extracted item that fails validation. It is dropped and logged."""


def attributes_to_dict(item: ExtractedItem) -> dict:
    attributes = {}
    for attribute in item.attributes:
        value = attribute.value.strip()
        # "2027" is more useful stored as the number 2027.
        attributes[attribute.name] = int(value) if value.isdigit() else value
    return attributes


def parse_profile_change(item: ExtractedItem) -> dict:
    """Turn a profile_correction into the User properties to set. Raises InvalidItem."""
    field_name = item.profile_field
    value = (item.profile_value or "").strip()
    if field_name is None or not value:
        raise InvalidItem("profile_correction without a field or value")

    if field_name in ("name", "birth_place"):
        return {field_name: value}

    if field_name == "dob":
        try:
            # The same rule as the onboarding form: 1900-01-01 through today.
            return {"dob": validate_dob(date.fromisoformat(value))}
        except ValueError as error:
            raise InvalidItem(f"invalid dob {value!r}: {error}")

    # birth_time
    try:
        return {"birth_time": time.fromisoformat(value), "birth_time_known": True}
    except ValueError:
        raise InvalidItem(f"invalid birth_time {value!r}")


class MemoryTask:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        driver: AsyncDriver,
        llm: LLMProvider,
    ):
        # The request's own database session is closed by the time this runs,
        # so the task opens a new one from the factory.
        self.session_factory = session_factory
        self.memories = MemoryRepository(driver)
        self.profiles = ProfileRepository(driver)
        self.extractor = MemoryExtractor(llm)

    @traceable(name="memory.task")
    async def run(self, job: MemoryJob) -> None:
        # --- Steps 2 and 3: extract, then write to Neo4j ---
        try:
            events = await self.extract_and_apply(job)
        except Exception:
            logger.exception("Memory task failed for message %s", job.message_id)
            await self.mark_failed(job)
            return

        # --- Step 4: record in Postgres, only after the Neo4j writes succeeded ---
        try:
            async with self.session_factory() as db:
                await MemoryEventRepository(db).record_done(job.message_id, events)
        except Exception:
            # Neo4j succeeded but Postgres did not. The memories exist in the brain;
            # only their audit rows and the 'done' status are missing.
            logger.exception(
                "INCONSISTENCY: memories for message %s were written to Neo4j but could not be "
                "recorded in Postgres. Affected memory ids: %s",
                job.message_id,
                [event.memory_id for event in events],
            )
            await self.mark_failed(job)

    async def mark_failed(self, job: MemoryJob) -> None:
        try:
            async with self.session_factory() as db:
                await MemoryEventRepository(db).set_status(job.message_id, "failed")
        except Exception:
            logger.exception("Could not mark message %s as failed", job.message_id)

    async def extract_and_apply(self, job: MemoryJob) -> list[MemoryEventRow]:
        user_id = str(job.user_id)
        existing = await self.memories.get_active_all(user_id)
        profile = await self.profiles.get_profile(user_id)
        today = datetime.now(timezone.utc).date()

        items = await self.extractor.extract(
            job.message, job.recent_messages, existing, profile, today
        )

        existing_ids = {memory.id for memory in existing}
        events = []
        profile_changed = False
        for item in items:
            if item.action == "skip":
                continue
            try:
                if item.kind == "profile_correction":
                    events.append(await self.apply_profile_correction(job, item))
                    profile_changed = True
                else:
                    events.append(await self.apply_memory(job, item, existing_ids))
            except InvalidItem as reason:
                # Never trust LLM output: an item that fails validation is dropped.
                logger.warning("Dropped an extracted item for message %s: %s", job.message_id, reason)

        if profile_changed:
            await self.mark_profile_complete_if_ready(job)
        return events

    @traceable(name="memory.apply_memory")
    async def apply_memory(
        self, job: MemoryJob, item: ExtractedItem, existing_ids: set[str]
    ) -> MemoryEventRow:
        if item.life_area not in LIFE_AREAS:
            raise InvalidItem(f"unknown life_area {item.life_area!r}")
        if not item.text.strip() or not item.title.strip():
            raise InvalidItem("empty title or text")
        if not (0 <= item.confidence <= 1 and 0 <= item.importance <= 1):
            raise InvalidItem("confidence or importance outside 0-1")
        if item.action == "update" and item.target_id not in existing_ids:
            raise InvalidItem(f"update of unknown memory {item.target_id!r}")

        now = datetime.now(timezone.utc)
        memory = MemoryNode(
            id=str(uuid.uuid4()),
            kind=item.kind,
            title=item.title.strip(),
            text=item.text.strip(),
            life_area=item.life_area,
            attributes=attributes_to_dict(item),
            confidence=item.confidence,
            importance=item.importance,
            created_at=now,
            updated_at=now,
            source_session_id=str(job.session_id),
            source_message_id=str(job.message_id),
        )

        user_id = str(job.user_id)
        if item.action == "update":
            # The old node is marked superseded and the new one takes its place.
            replaced = await self.memories.supersede(user_id, item.target_id, memory)
            if not replaced:
                raise InvalidItem(f"memory {item.target_id!r} was no longer active")
            action = "updated"
        else:
            await self.memories.create(user_id, memory)
            action = "created"

        return MemoryEventRow(
            message_id=job.message_id,
            user_id=job.user_id,
            action=action,
            memory_id=memory.id,
            kind=memory.kind,
            title=memory.title,
            life_area=memory.life_area,
        )

    @traceable(name="memory.apply_profile_correction")
    async def apply_profile_correction(self, job: MemoryJob, item: ExtractedItem) -> MemoryEventRow:
        changes = parse_profile_change(item)
        # A new date of birth can mean a new sun sign, so the zodiac link is recomputed.
        sun_sign = sun_sign_for(changes["dob"]) if "dob" in changes else None
        await self.profiles.update_from_chat(str(job.user_id), changes, sun_sign)

        return MemoryEventRow(
            message_id=job.message_id,
            user_id=job.user_id,
            action="profile_corrected",
            memory_id=None,
            kind="profile_correction",
            title=PROFILE_FIELD_TITLES[item.profile_field],
            life_area="general",
        )

    async def mark_profile_complete_if_ready(self, job: MemoryJob) -> None:
        """A profile given in chat counts as complete once name, dob and birth place are all known."""
        profile = await self.profiles.get_profile(str(job.user_id))
        if profile is None or not (profile.name and profile.dob and profile.birth_place):
            return
        async with self.session_factory() as db:
            await UserRepository(db).set_profile_complete(job.user_id)


def get_memory_task(request: Request) -> MemoryTask:
    """FastAPI dependency: a MemoryTask built from the app's shared connections."""
    state = request.app.state
    return MemoryTask(state.session_factory, state.neo4j, state.llm)
