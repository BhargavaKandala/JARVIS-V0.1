# voice/wakeword.py
"""Wake-word matching, and the single source of truth for the homophone list.

Whisper mishears "Jarvis" in consistent ways, so the list is deliberately fuzzy.
main.py imports from here -- do not reintroduce an inline copy.
"""
import re

WAKE_WORDS = ["jarvis", "jaress", "travis", "garbage"]


def detect_wake_word(text: str) -> bool:
    lowered = (text or "").lower()
    return any(word in lowered for word in WAKE_WORDS)


def strip_wake_word(text: str) -> str:
    """Remove the first wake word and any punctuation trailing it."""
    if not text:
        return ""
    pattern = "|".join(re.escape(word) for word in WAKE_WORDS)
    stripped = re.sub(rf"\b({pattern})\b[\s,.!?:;-]*", "", text, count=1, flags=re.IGNORECASE)
    return stripped.strip()
