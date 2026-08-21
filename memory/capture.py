# memory/capture.py
"""Post-turn automatic capture.

Runs on a single daemon thread fed by a queue, so nothing here can add latency
to the voice loop -- enqueue() returns immediately and the write happens after
Jarvis has finished speaking. Every write is independently guarded: a down
Obsidian or a down embedder must not cost you the memory row.
"""
import queue
import threading

from config.settings import ENABLE_AUTO_CAPTURE
from llm import hermes
from memory import store, vault, vector_store

INBOX_PROJECT = "Inbox"

_queue = queue.Queue()
_worker_started = False
_listener = None


def set_listener(fn):
    """Register fn(payload: dict) to run after each successful capture, or None to clear."""
    global _listener
    _listener = fn


def persist_capture(payload: dict, source_text: str):
    """Write one validated capture to SQLite and the vault. Returns the memory id."""
    entities = payload.get("entities") or []

    # 1. Entities. Identity is the (type, name) pair.
    entity_ids = []
    for entity in entities:
        try:
            entity_ids.append(store.get_or_create_entity(entity["type"], entity["name"]))
        except Exception as e:
            print(f"[capture] entity '{entity.get('name')}' failed: {e}")

    primary_id = entity_ids[0] if entity_ids else None

    # 2. Memory row. entity_id is how a memory attaches to an entity.
    memory_id = store.add_memory(
        kind=payload["kind"],
        content=payload["text"],
        title=entities[0]["name"] if entities else None,
        entity_id=primary_id,
        tags=[e["name"] for e in entities],
        source="auto_capture",
    )

    try:
        vector_store.index_memory(memory_id, payload["text"])
    except Exception as e:
        print(f"[capture] embedding failed: {e}")

    # 3. Co-occurrence edges. add_relationship is entity-to-entity only.
    for other_id in entity_ids[1:]:
        try:
            store.add_relationship(primary_id, other_id, "mentioned_with")
        except Exception as e:
            print(f"[capture] relationship failed: {e}")

    # 4. Commitments become due-dated tasks so list_overdue_tasks() finds them.
    if payload["kind"] == "commitment" and payload.get("due_date"):
        try:
            project = entities[0]["name"] if entities else INBOX_PROJECT
            store.add_task(project, payload["text"],
                           due_date=payload["due_date"], source_text=source_text)
        except Exception as e:
            print(f"[capture] task failed: {e}")

    # 5. Vault.
    try:
        line = vault.format_capture_line(payload["kind"], payload["text"],
                                         [e["name"] for e in entities])
        vault.append_daily_note(line)
    except Exception as e:
        print(f"[capture] daily note failed: {e}")

    for entity in entities:
        try:
            vault.ensure_entity_page(entity["name"], entity["type"])
        except Exception as e:
            print(f"[capture] entity page '{entity.get('name')}' failed: {e}")

    if _listener is not None:
        try:
            _listener(payload)
        except Exception as e:
            print(f"[capture] listener failed: {e}")

    return memory_id


def _worker():
    while True:
        user_text, reply = _queue.get()
        try:
            payload = hermes.extract_capture(user_text, reply)
            if payload is not None:
                persist_capture(payload, user_text)
        except Exception as e:
            # The worker must survive anything, or capture silently stops for the session.
            print(f"[capture] worker error: {e}")
        finally:
            _queue.task_done()


def enqueue(user_text: str, reply: str) -> None:
    """Queue one exchange for background capture. Never blocks, never raises."""
    global _worker_started
    if not ENABLE_AUTO_CAPTURE:
        return
    if not _worker_started:
        threading.Thread(target=_worker, daemon=True).start()
        _worker_started = True
    _queue.put((user_text, reply))
