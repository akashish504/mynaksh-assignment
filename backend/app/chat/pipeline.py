"""The chat pipeline: plain async steps that work on one TurnState.

    load -> history -> route -> retrieve -> build prompt -> generate -> save -> respond
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import Depends
from langsmith import traceable

from app.brain.memory_repository import MemoryRepository, get_memory_repository
from app.brain.profile_repository import ProfileRepository, get_profile_repository
from app.chat.prompt import build_prompt
from app.chat.retrievers import RETRIEVERS
from app.chat.state import TurnState
from app.classifier.base import Classifier
from app.classifier.router import get_classifier
from app.config import Settings, get_settings
from app.db.message_repository import MessageRepository, get_message_repository
from app.db.models import MessageRow, SessionRow, UserRow
from app.db.session_repository import DEFAULT_TITLE, SessionRepository, get_session_repository
from app.llm.base import LLMError, LLMProvider
from app.llm.litellm_provider import get_llm
from app.models.chat import ChatResponse

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 60
LLM_FAILURE_REPLY = "I'm having trouble answering right now. Please try again in a moment."


class SessionNotFound(Exception):
    """The session does not exist or belongs to another user."""


class ChatPipeline:
    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
        profiles: ProfileRepository,
        memories: MemoryRepository,
        classifier: Classifier,
        llm: LLMProvider,
        settings: Settings,
    ):
        self.sessions = sessions
        self.messages = messages
        self.profiles = profiles
        self.memories = memories
        self.classifier = classifier
        self.llm = llm
        self.settings = settings

    async def handle_turn(self, user: UserRow, session_id: uuid.UUID, message: str) -> ChatResponse:
        received_at = datetime.now(timezone.utc)

        session = await self.load_session(session_id, user.id)
        state = TurnState(
            user_id=str(user.id),
            session=session,
            message=message,
            history=[],
            profile_complete=user.profile_complete,
        )

        await self.load_profile(state)
        await self.load_history(state)
        await self.route(state)
        await self.retrieve(state)
        prompt = self.build_prompt(state)
        await self.generate(state, prompt)
        user_message = await self.save(state, received_at)

        return ChatResponse(
            response=state.reply,
            user_id=user.id,
            session_id=session.id,
            message_id=user_message.id,
            type="answer",
            options=None,
            context_used=state.context_used,
        )

    # --- Step 1: verify session ownership (Postgres), load profile and zodiac (Neo4j) ---

    @traceable(name="chat.load_session")
    async def load_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionRow:
        session = await self.sessions.get_for_user(session_id, user_id)
        if session is None:
            raise SessionNotFound()
        return session

    @traceable(name="chat.load_profile")
    async def load_profile(self, state: TurnState) -> None:
        try:
            state.profile = await self.profiles.get_profile(state.user_id)
        except Exception:
            # Neo4j is down: carry on and answer from the conversation history alone.
            logger.exception("Chat: Neo4j unavailable while loading the profile")
            state.brain_available = False

    # --- Step 2: short-term context (Postgres) ---

    @traceable(name="chat.load_history")
    async def load_history(self, state: TurnState) -> None:
        state.history = await self.messages.get_recent(
            state.session.id, self.settings.history_window
        )

    # --- Step 4: route ---

    @traceable(name="chat.route")
    async def route(self, state: TurnState) -> None:
        state.route = await self.classifier.route(state.history, state.message)

    # --- Step 6: retrieve only the relevant context (Neo4j) ---

    @traceable(name="chat.retrieve")
    async def retrieve(self, state: TurnState) -> None:
        if not state.brain_available:
            return
        retriever = RETRIEVERS[state.route.intent]
        try:
            await retriever(state, self.memories, self.settings)
        except Exception:
            logger.exception("Chat: Neo4j unavailable while retrieving memories")
            state.brain_available = False
            state.profile = None
            state.memories = []

    # --- Step 7: build the prompt (also fills context_used) ---

    @traceable(name="chat.build_prompt")
    def build_prompt(self, state: TurnState) -> list[dict]:
        today = datetime.now(timezone.utc).date()
        return build_prompt(state, today, self.settings.clarify_enabled)

    # --- Step 8: generate ---

    @traceable(name="chat.generate")
    async def generate(self, state: TurnState, prompt: list[dict]) -> None:
        try:
            state.reply = await self.llm.generate(prompt)
        except LLMError:
            # Every configured model failed. The user gets a normal, friendly answer
            # (HTTP 200), and nothing is claimed as "used".
            logger.exception("Chat: no model could generate a reply")
            state.reply = LLM_FAILURE_REPLY
            state.llm_failed = True
            state.context_used = []
            state.memories = []

    # --- Step 9: save both messages in one transaction (Postgres) ---

    def memory_status(self, state: TurnState) -> str:
        """Decide what happens to this user message in the background memory step."""
        if not state.brain_available:
            return "failed"  # Neo4j is down, so nothing can be stored
        gate_closed = (
            self.settings.memory_gate_enabled
            and state.route.has_durable_fact < self.settings.memory_gate_threshold
        )
        return "skipped" if gate_closed else "pending"

    @traceable(name="chat.save")
    async def save(self, state: TurnState, received_at: datetime) -> MessageRow:
        user_message = MessageRow(
            id=uuid.uuid4(),
            session_id=state.session.id,
            user_id=state.session.user_id,
            role="user",
            content=state.message,
            memory_status=self.memory_status(state),
            created_at=received_at,
        )
        assistant_message = MessageRow(
            id=uuid.uuid4(),
            session_id=state.session.id,
            user_id=state.session.user_id,
            role="assistant",
            content=state.reply,
            type="answer",
            context_used=state.context_used,
            used_memory_ids=[memory.id for memory in state.memories],
            route_intent=state.route.intent,
            route_areas=state.route.areas,
            # Later than the user message, so the pair always reads in the right order.
            created_at=datetime.now(timezone.utc),
        )

        # The session is titled after its first user message.
        is_first_message = state.session.title == DEFAULT_TITLE and not state.history
        new_title = state.message[:TITLE_MAX_LENGTH] if is_first_message else None

        await self.messages.save_turn(state.session, user_message, assistant_message, new_title)
        return user_message


def get_chat_pipeline(
    sessions: SessionRepository = Depends(get_session_repository),
    messages: MessageRepository = Depends(get_message_repository),
    profiles: ProfileRepository = Depends(get_profile_repository),
    memories: MemoryRepository = Depends(get_memory_repository),
    classifier: Classifier = Depends(get_classifier),
    llm: LLMProvider = Depends(get_llm),
    settings: Settings = Depends(get_settings),
) -> ChatPipeline:
    return ChatPipeline(sessions, messages, profiles, memories, classifier, llm, settings)
