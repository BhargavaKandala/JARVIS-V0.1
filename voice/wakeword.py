# voice/wakeword.py
"""Wake-word matching, and the single source of truth for the homophone list.

Whisper mishears "Jarvis" in consistent ways, so the list is deliberately fuzzy.
main.py imports from here -- do not reintroduce an inline copy.
"""
import re

WAKE_WORDS = ["jarvis", "jaress", "travis", "garbage"]

# "garbage" is a real, common English word -- unlike the other three homophones
# -- so treating it as a wake word anywhere in an utterance causes false wakes
# on ordinary speech ("the garbage disposal is broken"). Restrict it to the
# start of the utterance, which is where a wake word actually falls. The
# other homophones aren't ordinary words in this context, so they may still
# appear anywhere (users address the assistant mid-sentence too).
_AMBIGUOUS_WAKE_WORDS = {"garbage"}
_ANYWHERE_WAKE_WORDS = [w for w in WAKE_WORDS if w not in _AMBIGUOUS_WAKE_WORDS]

_TRAILING = r"[\s,.!?:;-]*"
_anywhere_pattern = "|".join(re.escape(w) for w in _ANYWHERE_WAKE_WORDS)
_leading_pattern = "|".join(re.escape(w) for w in sorted(_AMBIGUOUS_WAKE_WORDS))

# Single pattern shared by detect_wake_word and strip_wake_word so the two
# can never disagree about whether/where a wake word is present.
_WAKE_WORD_RE = re.compile(
    rf"^\s*(?:{_leading_pattern})\b{_TRAILING}|\b(?:{_anywhere_pattern})\b{_TRAILING}",
    re.IGNORECASE,
)


def detect_wake_word(text: str) -> bool:
    return _WAKE_WORD_RE.search(text or "") is not None


def strip_wake_word(text: str) -> str:
    """Remove the first wake word and any punctuation trailing it."""
    if not text:
        return ""
    stripped = _WAKE_WORD_RE.sub("", text, count=1)
    return stripped.strip()
