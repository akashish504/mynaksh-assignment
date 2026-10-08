"""The one state object that every pipeline step reads from and writes to."""

from dataclasses import dataclass, field
from typing import Literal

from app.classifier.base import RouteResult
from app.db.models import MessageRow, SessionRow
from app.models.memory import MemoryNode
from app.models.profile import Profile

# How much of the profile a retriever chose to put in the prompt:
#   "full"  - profile facts + sun sign with element and traits
#   "facts" - profile facts + sun sign name only (memory questions: no astrology flavour)
#   "name"  - the user's name only (small talk)
ProfileView = Literal["full", "facts", "name"]


@dataclass
class TurnState:
    user_id: str
    session: SessionRow
    message: str
    history: list[MessageRow]
    profile: Profile | None = None
    route: RouteResult | None = None
    memories: list[MemoryNode] = field(default_factory=list)
    context_used: list[str] = field(default_factory=list)
    reply: str | None = None

    # The Postgres flag. False means the reply should nudge the user to finish onboarding.
    profile_complete: bool = False
    profile_view: ProfileView = "full"
    # False when Neo4j could not be reached: the turn is answered from history alone.
    brain_available: bool = True
    # True when no model answered and the friendly "try again" reply was used.
    llm_failed: bool = False
