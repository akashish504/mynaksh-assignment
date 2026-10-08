"""Last-resort classifier: plain keyword rules. No network, so it cannot fail."""

import re

from langsmith import traceable

from app.classifier.base import RouteResult
from app.db.models import MessageRow

AREA_KEYWORDS: dict[str, list[str]] = {
    "career": ["career", "job", "work", "promotion", "boss", "office", "interview", "business", "profession"],
    "finance": ["money", "finance", "financial", "salary", "income", "savings", "invest", "loan", "debt", "wealth"],
    "relationships": ["relationship", "love", "partner", "marriage", "married", "dating", "boyfriend", "girlfriend", "husband", "wife", "friend"],
    "family": ["family", "mother", "father", "parents", "son", "daughter", "children", "kids", "brother", "sister", "home"],
    "health": ["health", "healthy", "sick", "illness", "fitness", "exercise", "diet", "sleep", "stress", "anxiety"],
    "education": ["study", "studies", "exam", "college", "university", "school", "course", "degree", "learn"],
    "spirituality": ["spiritual", "spirituality", "meditation", "meditate", "prayer", "faith", "karma", "soul"],
    "travel": ["travel", "trip", "journey", "abroad", "relocate", "relocation", "vacation", "visa"],
}

MEMORY_QUERY_PHRASES = ["what do you remember", "do you remember", "what do you know about me", "what have i told you"]
PROFILE_QUERY_PHRASES = ["my sign", "my zodiac", "my sun sign", "my birth", "when was i born", "where was i born", "what is my name", "what's my name"]
FOLLOWUP_PHRASES = ["why do you say", "why is that", "what do you mean", "tell me more", "can you explain", "explain that", "how so", "go on"]
SMALLTALK_MESSAGES = ["hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "good morning", "good night"]

# Rules cannot judge confidence, so a fixed middling value is reported.
RULES_CONFIDENCE = 0.5


def contains_word(text: str, word: str) -> bool:
    # \b = word boundary, so "work" matches "work" and "work?" but not "network".
    return re.search(rf"\b{re.escape(word)}", text) is not None


class RulesClassifier:
    @traceable(name="classifier.rules")
    async def route(self, history: list[MessageRow], message: str) -> RouteResult:
        text = message.lower().strip()
        bare = text.strip(" !.?,")

        if any(phrase in text for phrase in MEMORY_QUERY_PHRASES):
            intent = "memory_query"
        elif any(phrase in text for phrase in PROFILE_QUERY_PHRASES):
            intent = "profile_query"
        elif bare in SMALLTALK_MESSAGES:
            intent = "smalltalk"
        elif history and (bare == "why" or any(phrase in text for phrase in FOLLOWUP_PHRASES)):
            # A follow-up needs something to follow, hence the `history` check.
            intent = "followup"
        else:
            intent = "general"

        areas = [
            area
            for area, keywords in AREA_KEYWORDS.items()
            if any(contains_word(text, keyword) for keyword in keywords)
        ]
        return RouteResult(
            intent=intent,
            intent_confidence=RULES_CONFIDENCE,
            areas=areas or ["general"],
            # Rules cannot tell whether a fact is worth keeping, so the memory gate
            # is left open and the extraction step decides.
            has_durable_fact=1.0,
            source="rules",
        )
