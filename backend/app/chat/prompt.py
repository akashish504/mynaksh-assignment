"""Builds the LLM prompt from the selected context, as labeled blocks:

    [SYSTEM]  persona + rules
    [PROFILE] the profile fields the retriever allowed
    [MEMORY]  one line per selected memory
    [HISTORY] recent messages
    [USER]    the current message

A block with nothing in it is left out entirely. `context_used` is built here,
at the same moment each piece is added, so it lists exactly what was injected.
"""

from datetime import date, datetime

from app.chat.state import TurnState

PERSONA = "You are a warm, practical astrology guide for the MyNaksh app."

MEMORY_PERSONA = (
    "You are a warm, practical assistant for the MyNaksh app. The user is asking what you "
    "remember about them. Tell them plainly what is in the PROFILE and MEMORY blocks. "
    "Do not add astrological interpretation."
)

ASTROLOGY_RULE = (
    "Your astrology flavour comes only from the sun sign, element and traits in the PROFILE "
    "block. Do not claim planetary positions, charts or calculations you were not given."
)
RELEVANCE_RULE = (
    "Use the facts in the PROFILE and MEMORY blocks only when they are relevant to the question."
)
NO_INVENTION_RULE = (
    "Never invent facts about the user. If something is not in the PROFILE, MEMORY or HISTORY "
    "blocks, say that you don't know it yet."
)
BIRTH_TIME_RULE = (
    'If the birth time is "unknown", do not give timing that depends on it; say that the '
    "birth time is needed for that."
)
INCOMPLETE_PROFILE_RULE = (
    "The user has not completed their birth details. Answer generally, and suggest they "
    "complete their birth details in their profile to get personalised guidance."
)
NO_CLARIFY_RULE = "Do not ask clarifying questions. Make a reasonable assumption and state it briefly."
CLARIFY_RULE = (
    "If the question is ambiguous and the answer depends on it, ask one short clarifying question."
)
BREVITY_RULE = "Keep your reply short and concrete: a few short paragraphs at most."


def relative_date(then: datetime, today: date) -> str:
    days = (today - then.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = days // 7
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"
    if days < 365:
        months = days // 30
        return "1 month ago" if months == 1 else f"{months} months ago"
    years = days // 365
    return "1 year ago" if years == 1 else f"{years} years ago"


def build_system_block(state: TurnState, today: date, clarify_enabled: bool) -> str:
    is_memory_question = state.route.intent == "memory_query"
    lines = [
        MEMORY_PERSONA if is_memory_question else PERSONA,
        f"Today's date is {today.isoformat()} (UTC).",
        "",
        "Rules:",
    ]
    rules = []
    if not is_memory_question:
        rules.append(ASTROLOGY_RULE)
    rules.append(RELEVANCE_RULE)
    rules.append(NO_INVENTION_RULE)
    if not is_memory_question:
        rules.append(BIRTH_TIME_RULE)
    # Only when Neo4j is reachable: if it is down we cannot tell, so we do not nudge.
    if state.brain_available and not state.profile_complete:
        rules.append(INCOMPLETE_PROFILE_RULE)
    rules.append(CLARIFY_RULE if clarify_enabled else NO_CLARIFY_RULE)
    rules.append(BREVITY_RULE)
    lines.extend(f"- {rule}" for rule in rules)
    return "[SYSTEM]\n" + "\n".join(lines)


def build_profile_block(state: TurnState) -> str | None:
    profile = state.profile
    if profile is None:
        return None

    lines = []
    if profile.name:
        lines.append(f"Name: {profile.name}")

    if state.profile_view != "name":
        if profile.dob:
            lines.append(f"Date of birth: {profile.dob.isoformat()}")
        if profile.birth_place:
            lines.append(f"Birth place: {profile.birth_place}")
        if profile.birth_time_known and profile.birth_time:
            lines.append(f"Birth time: {profile.birth_time.strftime('%H:%M')}")
        else:
            lines.append("Birth time: unknown")

    if lines:
        state.context_used.append("user_profile")

    if profile.zodiac is not None and state.profile_view != "name":
        if state.profile_view == "full":
            traits = ", ".join(profile.zodiac.traits)
            lines.append(f"Sun sign: {profile.zodiac.name} ({profile.zodiac.element}) - traits: {traits}")
        else:
            lines.append(f"Sun sign: {profile.zodiac.name}")
        state.context_used.append("zodiac")

    if not lines:
        return None
    return "[PROFILE]\n" + "\n".join(lines)


def build_memory_block(state: TurnState, today: date) -> str | None:
    if not state.memories:
        return None
    lines = []
    for memory in state.memories:
        stated = relative_date(memory.created_at, today)
        lines.append(f"- {memory.kind} ({memory.life_area}): {memory.text} (stated {stated})")
        state.context_used.append(f"{memory.kind}:{memory.id}")
    return "[MEMORY]\n" + "\n".join(lines)


def build_history_block(state: TurnState) -> str | None:
    if not state.history:
        return None
    state.context_used.append("history")
    return "[HISTORY]\n" + "\n".join(f"{row.role}: {row.content}" for row in state.history)


def build_prompt(state: TurnState, today: date, clarify_enabled: bool) -> list[dict]:
    """Return the chat messages for the LLM and fill `state.context_used`.

    The blocks are built in the order their labels appear in `context_used`:
    profile, zodiac, history, then one entry per memory.
    """
    state.context_used = []
    system_block = build_system_block(state, today, clarify_enabled)
    profile_block = build_profile_block(state)
    history_block = build_history_block(state)
    memory_block = build_memory_block(state, today)
    user_block = f"[USER]\n{state.message}"

    system_content = [system_block, profile_block, memory_block]
    user_content = [history_block, user_block]
    return [
        {"role": "system", "content": "\n\n".join(block for block in system_content if block)},
        {"role": "user", "content": "\n\n".join(block for block in user_content if block)},
    ]
