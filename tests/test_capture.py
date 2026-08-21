import pytest

from memory import capture


@pytest.fixture(autouse=True)
def no_vault_writes(monkeypatch):
    """persist_capture must be testable without Obsidian running."""
    monkeypatch.setattr(capture.vault, "append_daily_note", lambda *a, **k: True)
    monkeypatch.setattr(capture.vault, "ensure_entity_page", lambda *a, **k: True)
    monkeypatch.setattr(capture.vector_store, "index_memory", lambda *a, **k: None)


def _payload(**overrides):
    base = {"kind": "fact", "text": "Bhargava prefers dark mode",
            "entities": [], "due_date": None}
    base.update(overrides)
    return base


def test_persists_a_memory_row(temp_db):
    memory_id = capture.persist_capture(_payload(), "I like dark mode")
    memory = temp_db.get_memory(memory_id)
    assert memory["content"] == "Bhargava prefers dark mode"
    assert memory["kind"] == "fact"


def test_creates_entities_with_their_declared_type(temp_db):
    capture.persist_capture(
        _payload(entities=[{"name": "Ravi", "type": "person"}]), "src")
    rows = temp_db._get_conn().execute("SELECT type, name FROM entities").fetchall()
    assert (rows[0]["type"], rows[0]["name"]) == ("person", "Ravi")


def test_links_memory_to_the_primary_entity(temp_db):
    memory_id = capture.persist_capture(
        _payload(entities=[{"name": "Ravi", "type": "person"},
                           {"name": "Auth Refactor", "type": "project"}]), "src")
    primary_id = temp_db.get_or_create_entity("person", "Ravi")
    assert temp_db.get_memory(memory_id)["entity_id"] == primary_id


def test_single_entity_creates_no_relationship(temp_db):
    capture.persist_capture(_payload(entities=[{"name": "Ravi", "type": "person"}]), "src")
    count = temp_db._get_conn().execute("SELECT COUNT(*) c FROM relationships").fetchone()["c"]
    assert count == 0


def test_two_entities_create_a_mentioned_with_edge(temp_db):
    capture.persist_capture(
        _payload(entities=[{"name": "Ravi", "type": "person"},
                           {"name": "Auth Refactor", "type": "project"}]), "src")
    row = temp_db._get_conn().execute(
        "SELECT relation_type FROM relationships").fetchone()
    assert row["relation_type"] == "mentioned_with"


def test_repeated_capture_does_not_duplicate_edges(temp_db):
    pair = [{"name": "Ravi", "type": "person"}, {"name": "Auth Refactor", "type": "project"}]
    capture.persist_capture(_payload(entities=pair), "src")
    capture.persist_capture(_payload(entities=pair), "src")
    count = temp_db._get_conn().execute("SELECT COUNT(*) c FROM relationships").fetchone()["c"]
    assert count == 1


def test_commitment_with_due_date_creates_a_task(temp_db):
    capture.persist_capture(
        _payload(kind="commitment", text="Finish the auth refactor",
                 entities=[{"name": "Auth Refactor", "type": "project"}],
                 due_date="2026-08-11"),
        "I'll finish the auth refactor by Tuesday")
    row = temp_db._get_conn().execute(
        "SELECT title, due_date, source_text FROM tasks").fetchone()
    assert row["due_date"] == "2026-08-11"
    assert row["source_text"] == "I'll finish the auth refactor by Tuesday"


def test_commitment_without_entities_lands_in_inbox(temp_db):
    capture.persist_capture(
        _payload(kind="commitment", text="Call the bank", due_date="2026-08-11"), "src")
    row = temp_db._get_conn().execute(
        "SELECT p.name FROM tasks t JOIN projects p ON p.id = t.project_id").fetchone()
    assert row["name"] == "Inbox"


def test_commitment_without_due_date_creates_no_task(temp_db):
    capture.persist_capture(_payload(kind="commitment", text="Call the bank"), "src")
    count = temp_db._get_conn().execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
    assert count == 0


def test_non_commitment_with_due_date_creates_no_task(temp_db):
    capture.persist_capture(_payload(kind="fact", due_date="2026-08-11"), "src")
    count = temp_db._get_conn().execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
    assert count == 0


def test_vault_failure_does_not_lose_the_memory(temp_db, monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("Obsidian is down")
    monkeypatch.setattr(capture.vault, "append_daily_note", boom)

    memory_id = capture.persist_capture(_payload(), "src")

    assert temp_db.get_memory(memory_id) is not None


def test_embedding_failure_does_not_lose_the_memory(temp_db, monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("Ollama is down")
    monkeypatch.setattr(capture.vector_store, "index_memory", boom)

    memory_id = capture.persist_capture(_payload(), "src")

    assert temp_db.get_memory(memory_id) is not None


def test_listener_is_notified_after_a_capture(temp_db):
    seen = []
    capture.set_listener(seen.append)
    try:
        capture.persist_capture(_payload(), "src")
    finally:
        capture.set_listener(None)
    assert seen[0]["text"] == "Bhargava prefers dark mode"


def test_a_raising_listener_does_not_break_capture(temp_db):
    def boom(_):
        raise RuntimeError("GUI exploded")
    capture.set_listener(boom)
    try:
        memory_id = capture.persist_capture(_payload(), "src")
    finally:
        capture.set_listener(None)
    assert memory_id is not None


def test_enqueue_persists_via_background_worker(temp_db, monkeypatch):
    """Deterministic worker test: no sleep(), synchronize on queue.join()."""
    monkeypatch.setattr(capture, "ENABLE_AUTO_CAPTURE", True)
    monkeypatch.setattr(
        capture.hermes, "extract_capture",
        lambda user_text, reply: _payload(text="captured via worker"),
    )

    capture.enqueue("some user text", "some reply")
    capture._queue.join()

    rows = temp_db._get_conn().execute("SELECT content FROM memories").fetchall()
    assert [r["content"] for r in rows] == ["captured via worker"]


def test_memory_row_failure_does_not_block_later_steps(temp_db, monkeypatch):
    """A DB lock (or a malformed entity dict) inside store.add_memory must not
    skip the co-occurrence edges, the daily-note append, the entity pages, or
    the embedding step (which must be skipped, not called with None) that
    follow it in persist_capture. persist_capture itself must not raise --
    the direct call below is the proof: an uncaught exception here would fail
    this test."""
    def boom(**kwargs):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(capture.store, "add_memory", boom)

    daily_note_calls = []
    entity_page_calls = []
    index_calls = []
    monkeypatch.setattr(capture.vault, "append_daily_note",
                        lambda *a, **k: daily_note_calls.append((a, k)) or True)
    monkeypatch.setattr(capture.vault, "ensure_entity_page",
                        lambda *a, **k: entity_page_calls.append((a, k)) or True)
    monkeypatch.setattr(capture.vector_store, "index_memory",
                        lambda *a, **k: index_calls.append((a, k)))

    pair = [{"name": "Ravi", "type": "person"}, {"name": "Auth Refactor", "type": "project"}]
    memory_id = capture.persist_capture(_payload(entities=pair), "src")

    assert memory_id is None
    assert index_calls == []  # embedding is skipped, not called with memory_id=None

    ravi_id = temp_db.get_or_create_entity("person", "Ravi")
    auth_id = temp_db.get_or_create_entity("project", "Auth Refactor")
    row = temp_db._get_conn().execute(
        "SELECT from_entity_id, to_entity_id, relation_type FROM relationships").fetchone()
    assert (row["from_entity_id"], row["to_entity_id"], row["relation_type"]) == \
        (ravi_id, auth_id, "mentioned_with")

    assert len(daily_note_calls) == 1
    assert entity_page_calls == [(("Ravi", "person"), {}), (("Auth Refactor", "project"), {})]


def test_duplicate_entity_in_payload_creates_no_self_relationship(temp_db):
    capture.persist_capture(
        _payload(entities=[{"name": "Ravi", "type": "person"},
                           {"name": "Ravi", "type": "person"}]), "src")
    ravi_id = temp_db.get_or_create_entity("person", "Ravi")
    rows = temp_db._get_conn().execute(
        "SELECT from_entity_id, to_entity_id FROM relationships").fetchall()
    assert rows == []
    assert temp_db._get_conn().execute(
        "SELECT COUNT(*) c FROM entities WHERE name = 'Ravi'").fetchone()["c"] == 1


def test_worker_survives_extract_capture_raising(temp_db, monkeypatch):
    """One exchange raising inside the worker must not stop later exchanges from
    being captured -- the daemon thread must never die."""
    monkeypatch.setattr(capture, "ENABLE_AUTO_CAPTURE", True)

    calls = {"n": 0}

    def flaky(user_text, reply):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Hermes fell over")
        return _payload(text="second call survived")

    monkeypatch.setattr(capture.hermes, "extract_capture", flaky)

    capture.enqueue("first text", "first reply")
    capture._queue.join()
    capture.enqueue("second text", "second reply")
    capture._queue.join()

    rows = temp_db._get_conn().execute("SELECT content FROM memories").fetchall()
    assert [r["content"] for r in rows] == ["second call survived"]
