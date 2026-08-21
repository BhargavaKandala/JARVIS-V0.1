from datetime import date

from llm import hermes


def test_parses_a_well_formed_payload():
    raw = ('{"capture": true, "kind": "commitment", "text": "Finish auth by Tuesday", '
           '"entities": [{"name": "Auth Refactor", "type": "project"}], "due_date": "2026-08-11"}')
    # Fixed `today` earlier than the payload's due_date, so this test doesn't depend on
    # (and can't be broken by) the real system clock ever passing 2026-08-11.
    result = hermes.parse_capture(raw, today=date(2026, 8, 1))
    assert result["kind"] == "commitment"
    assert result["text"] == "Finish auth by Tuesday"
    assert result["entities"] == [{"name": "Auth Refactor", "type": "project"}]
    assert result["due_date"] == "2026-08-11"


def test_capture_false_returns_none():
    assert hermes.parse_capture('{"capture": false}') is None


def test_malformed_json_returns_none():
    assert hermes.parse_capture("not json at all") is None
    assert hermes.parse_capture('{"capture": true, ') is None
    assert hermes.parse_capture("") is None


def test_strips_markdown_code_fences():
    raw = '```json\n{"capture": true, "kind": "fact", "text": "Coffee is good"}\n```'
    result = hermes.parse_capture(raw)
    assert result["text"] == "Coffee is good"


def test_extracts_json_embedded_in_prose():
    raw = 'Sure! Here is the JSON:\n{"capture": true, "kind": "fact", "text": "Coffee is good"}\nHope that helps.'
    result = hermes.parse_capture(raw)
    assert result["text"] == "Coffee is good"


def test_missing_text_returns_none():
    assert hermes.parse_capture('{"capture": true, "kind": "fact"}') is None
    assert hermes.parse_capture('{"capture": true, "kind": "fact", "text": "   "}') is None


def test_unknown_kind_returns_none():
    assert hermes.parse_capture('{"capture": true, "kind": "gossip", "text": "x"}') is None


def test_missing_kind_returns_none():
    assert hermes.parse_capture('{"capture": true, "text": "x"}') is None


def test_bare_string_entities_default_to_topic():
    raw = '{"capture": true, "kind": "fact", "text": "x", "entities": ["Ravi"]}'
    result = hermes.parse_capture(raw)
    assert result["entities"] == [{"name": "Ravi", "type": "topic"}]


def test_entity_with_unknown_type_falls_back_to_topic():
    raw = '{"capture": true, "kind": "fact", "text": "x", "entities": [{"name": "Ravi", "type": "alien"}]}'
    result = hermes.parse_capture(raw)
    assert result["entities"] == [{"name": "Ravi", "type": "topic"}]


def test_entities_default_to_empty_list():
    result = hermes.parse_capture('{"capture": true, "kind": "fact", "text": "x"}')
    assert result["entities"] == []


def test_nameless_and_blank_entities_are_dropped():
    raw = ('{"capture": true, "kind": "fact", "text": "x", '
           '"entities": [{"type": "person"}, {"name": "  ", "type": "person"}, "Ravi"]}')
    result = hermes.parse_capture(raw)
    assert result["entities"] == [{"name": "Ravi", "type": "topic"}]


def test_due_date_defaults_to_none():
    result = hermes.parse_capture('{"capture": true, "kind": "fact", "text": "x"}')
    assert result["due_date"] is None


def test_non_iso_due_date_is_discarded():
    raw = '{"capture": true, "kind": "commitment", "text": "x", "due_date": "next Tuesday"}'
    assert hermes.parse_capture(raw)["due_date"] is None


def test_capture_key_missing_is_treated_as_no_capture():
    assert hermes.parse_capture('{"kind": "fact", "text": "x"}') is None


def test_extract_capture_returns_none_when_llm_raises(monkeypatch):
    class _RaisingLLM:
        def invoke(self, messages):
            raise RuntimeError("Ollama unreachable")

    monkeypatch.setattr(hermes, "_get_llm", lambda: _RaisingLLM())
    result = hermes.extract_capture("some user text", "some reply")
    assert result is None


def test_past_due_date_is_dropped_but_rest_of_payload_survives():
    raw = ('{"capture": true, "kind": "commitment", "text": "Finish the auth refactor", '
           '"entities": [{"name": "Auth Refactor", "type": "project"}], "due_date": "2026-08-01"}')
    result = hermes.parse_capture(raw, today=date(2026, 8, 22))
    assert result["due_date"] is None
    assert result["kind"] == "commitment"
    assert result["text"] == "Finish the auth refactor"
    assert result["entities"] == [{"name": "Auth Refactor", "type": "project"}]


def test_due_date_equal_to_today_is_kept():
    raw = '{"capture": true, "kind": "commitment", "text": "x", "due_date": "2026-08-22"}'
    result = hermes.parse_capture(raw, today=date(2026, 8, 22))
    assert result["due_date"] == "2026-08-22"


def test_future_due_date_is_kept():
    raw = '{"capture": true, "kind": "commitment", "text": "x", "due_date": "2026-08-23"}'
    result = hermes.parse_capture(raw, today=date(2026, 8, 22))
    assert result["due_date"] == "2026-08-23"


def test_extract_capture_prompt_includes_todays_weekday(monkeypatch):
    """Guards the {{/}} escaping in CAPTURE_PROMPT: if the new format keys broke it,
    CAPTURE_PROMPT.format(...) would raise before the LLM is ever invoked."""
    captured = {}

    class _FakeResponse:
        content = '{"capture": false}'

    class _FakeLLM:
        def invoke(self, messages):
            captured["prompt"] = messages[0].content
            return _FakeResponse()

    monkeypatch.setattr(hermes, "_get_llm", lambda: _FakeLLM())

    result = hermes.extract_capture("some user text", "some reply")

    assert result is None
    today_weekday = date.today().strftime("%A")
    assert today_weekday in captured["prompt"]
    assert "some user text" in captured["prompt"]
    assert "some reply" in captured["prompt"]
