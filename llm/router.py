# llm/router.py
"""Single entry point for answering one conversation turn.

All conversation goes to Gemini (llm.gemini.ask_gemini). Hermes is
capture-only now -- see llm/hermes.py's module docstring for why: benchmarked
against the live model, only 1 of 6 requests that needed Gemini actually
escalated, and the failures invented plausible-but-wrong tool calls with real
side effects (a weather question opened YouTube). The project owner decided
Hermes stays out of the live conversation path.

This module is deliberately small: it is the one seam main.py calls, so
error handling for cloud failures (quota exhaustion, any other exception)
lives in exactly one place instead of being scattered through the GUI/voice
loop. handle() must never raise -- it is called from the voice loop.
"""
from llm.gemini import ask_gemini

RATE_LIMIT_REPLY = "Boss, Google is rate limiting my API. Give me a moment to cool down."
GENERIC_ERROR_REPLY = "I hit an error in my cognitive engine."


def handle(text: str) -> str:
    """Answer one turn. Always returns a string that is safe to speak aloud."""
    try:
        return ask_gemini(text)
    except Exception as e:
        message = str(e).upper()
        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            return RATE_LIMIT_REPLY
        print(f"[router] gemini failed: {e}")
        return GENERIC_ERROR_REPLY
