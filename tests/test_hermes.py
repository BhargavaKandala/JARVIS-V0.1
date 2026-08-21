from llm import hermes


def test_parses_a_well_formed_payload():
    raw = ('{"capture": true, "kind": "commitment", "text": "Finish auth by Tuesday", '
           '"entities": [{"name": "Auth Refactor", "type": "project"}], "due_date": "2026-08-11"}')
    result = hermes.parse_capture(raw)
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
