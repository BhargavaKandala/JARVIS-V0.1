import pytest

from llm import router


def test_normal_reply_is_passed_through_unchanged(monkeypatch):
    monkeypatch.setattr(router, "ask_gemini", lambda text: f"gemini: {text}")
    assert router.handle("what is the weather") == "gemini: what is the weather"


def test_rate_limit_429_returns_the_rate_limit_constant(monkeypatch):
    def boom(text):
        raise RuntimeError("429 Client Error: Too Many Requests")
    monkeypatch.setattr(router, "ask_gemini", boom)

    assert router.handle("hello") == router.RATE_LIMIT_REPLY


def test_resource_exhausted_returns_the_rate_limit_constant(monkeypatch):
    def boom(text):
        raise RuntimeError("google.api_core.exceptions.ResourceExhausted: 429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(router, "ask_gemini", boom)

    assert router.handle("hello") == router.RATE_LIMIT_REPLY


def test_rate_limit_detection_is_case_insensitive(monkeypatch):
    def boom(text):
        raise RuntimeError("quota exceeded: resource_exhausted")
    monkeypatch.setattr(router, "ask_gemini", boom)

    assert router.handle("hello") == router.RATE_LIMIT_REPLY


def test_other_exception_returns_the_generic_constant(monkeypatch):
    def boom(text):
        raise ConnectionError("network unreachable")
    monkeypatch.setattr(router, "ask_gemini", boom)

    assert router.handle("hello") == router.GENERIC_ERROR_REPLY


def test_handle_never_raises(monkeypatch):
    def boom(text):
        raise ValueError("something unexpected")
    monkeypatch.setattr(router, "ask_gemini", boom)

    try:
        result = router.handle("hello")
    except Exception as e:
        pytest.fail(f"handle() raised {e!r}, it must never raise")

    assert isinstance(result, str)


# --- history-reset-on-failure --------------------------------------------
#
# gemini.py's messages[-20:] trim can slice a ToolMessage away from the
# AIMessage carrying its tool_call, and since ask_gemini raises before
# reassigning conversation_history, the corrupt tail persists and wedges
# every later turn until restart. router.handle must reset it on any
# raise so the next turn starts clean -- but must NOT touch it on success,
# since gemini.py owns the history in the normal path.

def test_history_is_reset_when_ask_gemini_raises(monkeypatch):
    router._gemini.conversation_history = ["corrupt", "tail"]

    def boom(text):
        raise RuntimeError("Gemini rejected the function response")
    monkeypatch.setattr(router, "ask_gemini", boom)

    router.handle("hello")

    assert router._gemini.conversation_history == []


def test_history_is_untouched_on_a_successful_turn(monkeypatch):
    sentinel = ["existing", "history"]
    router._gemini.conversation_history = sentinel
    monkeypatch.setattr(router, "ask_gemini", lambda text: "a fine reply")

    router.handle("hello")

    assert router._gemini.conversation_history is sentinel
