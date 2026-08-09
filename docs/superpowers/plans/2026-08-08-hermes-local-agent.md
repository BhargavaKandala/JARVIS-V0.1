# Hermes Local Agent + Obsidian Second Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Nous Hermes 3 8B as a local Ollama-backed brain that handles common requests without a network call, and make the Obsidian vault fill itself with linked daily notes and entity pages after every conversation.

**Architecture:** A router calls Hermes first with a small 8-tool subset; Hermes either answers or calls an `escalate_to_gemini` tool, which hands the original text to the existing untouched `ask_gemini` multi-hop loop. After playback, a background thread asks Hermes to extract anything worth keeping as strict JSON and writes it to SQLite plus the Obsidian vault. Embeddings move from Gemini to local `nomic-embed-text` so capture never touches the network.

**Tech Stack:** Python 3.12, `uv`, LangChain, `langchain-ollama` (new), `langchain-google-genai` (existing), Ollama (`hermes3:8b`, `nomic-embed-text`), SQLite, CustomTkinter, pytest (new).

**Spec:** `docs/superpowers/specs/2026-08-08-hermes-agent-design.md`

## Global Constraints

- Python `>=3.12`. Package manager is `uv`. Regenerate `requirements.txt` with `uv pip compile pyproject.toml -o requirements.txt` after any `pyproject.toml` edit.
- Branch is `feat/hermes-local-agent`. Do not commit to `main`. The working tree has unrelated pre-existing modifications — **`git add` only the exact files listed in each Commit step**, never `git add -A` or `git add .`.
- `llm/gemini.py` must not change. `ask_gemini` is preserved verbatim as the escalation target.
- Hardware ceiling: 4096 MiB VRAM, 15.3 GB RAM. Do not introduce a second resident model beyond `hermes3:8b` + `nomic-embed-text`.
- Hermes is bound to exactly the 8 tools in `HERMES_TOOLS`. Gemini keeps all 26. Do not grow the Hermes tier.
- Every vault write and every DB write in the capture path is independently `try/except`ed. One failure must never block the others, and none may propagate into the voice loop.
- The capture worker thread must never die. Catch at the consumer loop boundary.
- Tkinter widgets are touched only from the main thread. Any GUI update originating in the capture thread goes through `self.after(0, ...)`.
- Entity identity is the `(type, name)` pair — `store.get_or_create_entity(type_, name)` takes the type first.
- `store.add_relationship` is entity-to-entity only. A memory attaches to an entity via `add_memory(entity_id=...)`.
- No new runtime dependency other than `langchain-ollama`. No vector database.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `config/settings.py` | Modify | Add `OLLAMA_HOST`, `HERMES_MODEL`, `EMBED_MODEL`, `ENABLE_AUTO_CAPTURE` |
| `pyproject.toml` | Modify | Add `langchain-ollama`, `pytest` |
| `tests/conftest.py` | Create | `temp_db` fixture isolating `memory/store.py` onto a tmp SQLite file |
| `memory/vault.py` | Create | Obsidian REST writer + pure path/markdown formatting helpers |
| `memory/vector_store.py` | Modify | Ollama embedder, `model` filter in `search()` |
| `scripts/reindex_embeddings.py` | Create | One-shot re-embed migration with DB backup |
| `llm/hermes.py` | Create | Ollama chat client, tier-1 tool list, `escalate_to_gemini`, capture JSON parsing |
| `memory/capture.py` | Create | Queue + daemon worker + `persist_capture` write pipeline |
| `llm/router.py` | Create | Hermes-first orchestration with escalation to `ask_gemini` |
| `voice/wakeword.py` | Modify | Real wake-word matching and stripping (currently dead code) |
| `main.py` | Modify | Use router, follow-up window, capture enqueue, brain indicator, live vault panel |
| `skills/memory_tools.py` | Modify | Delegate raw Obsidian HTTP to `memory/vault.py`; tool behavior unchanged |

---

### Task 1: Dependencies, settings, and test harness

**Files:**
- Modify: `pyproject.toml:7-29`
- Modify: `config/settings.py:11`
- Create: `tests/conftest.py`
- Create: `tests/test_settings.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `config.settings.OLLAMA_HOST: str`, `config.settings.HERMES_MODEL: str`, `config.settings.EMBED_MODEL: str`, `config.settings.ENABLE_AUTO_CAPTURE: bool`. A pytest fixture `temp_db` yielding the `memory.store` module bound to a temporary SQLite file.

- [ ] **Step 1: Pull the Ollama models**

These are large downloads; start them before anything else.

```powershell
ollama pull hermes3:8b
ollama pull nomic-embed-text
```

Verify:

```powershell
ollama list
```

Expected: rows for both `hermes3:8b` and `nomic-embed-text`.

- [ ] **Step 2: Add dependencies to pyproject.toml**

In `pyproject.toml`, add two entries to the `dependencies` list, keeping it alphabetically sorted:

```toml
    "langchain-ollama>=0.3.0",
```

goes immediately after the `"langchain-google-genai>=4.2.4",` line, and:

```toml
    "pytest>=8.0.0",
```

goes immediately after `"pyaudio>=0.2.14",`.

- [ ] **Step 3: Install and regenerate requirements.txt**

```powershell
uv pip compile pyproject.toml -o requirements.txt
uv pip install -r requirements.txt
```

Expected: completes without a resolution error, and `requirements.txt` now contains `langchain-ollama`.

- [ ] **Step 4: Write the failing settings test**

Create `tests/test_settings.py`:

```python
from config import settings


def test_ollama_defaults_present():
    assert settings.OLLAMA_HOST == "http://127.0.0.1:11434"
    assert settings.HERMES_MODEL == "hermes3:8b"
    assert settings.EMBED_MODEL == "nomic-embed-text"


def test_auto_capture_defaults_on():
    assert settings.ENABLE_AUTO_CAPTURE is True
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL with `AttributeError: module 'config.settings' has no attribute 'OLLAMA_HOST'`.

- [ ] **Step 6: Add the settings**

In `config/settings.py`, insert after the `GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")` line:

```python
# --- Local Hermes brain (Ollama) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
HERMES_MODEL = os.getenv("HERMES_MODEL", "hermes3:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
ENABLE_AUTO_CAPTURE = os.getenv("ENABLE_AUTO_CAPTURE", "true").lower() == "true"
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 2 passed.

- [ ] **Step 8: Create the shared test fixture**

`memory/store.py` caches a module-level connection in `_conn` and resolves `DB_PATH` at module import. Tests must not write to the real `data/jarvis.db`. Create `tests/conftest.py`:

```python
import pytest

from memory import store as _store


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point memory.store at a throwaway SQLite file for the duration of one test."""
    monkeypatch.setattr(_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(_store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(_store, "_conn", None)

    yield _store

    if _store._conn is not None:
        _store._conn.close()
    _store._conn = None
```

- [ ] **Step 9: Verify the fixture isolates the database**

Create `tests/test_conftest_fixture.py`:

```python
def test_temp_db_starts_empty(temp_db):
    assert temp_db.list_memories() == []


def test_temp_db_accepts_writes(temp_db):
    memory_id = temp_db.add_memory(kind="semantic", content="hello")
    assert temp_db.get_memory(memory_id)["content"] == "hello"
```

Run: `uv run pytest tests/ -v`
Expected: 4 passed. Confirm `data/jarvis.db` was **not** created or modified:

```powershell
git status --short data/
```

Expected: no output for `data/`.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml requirements.txt config/settings.py tests/conftest.py tests/test_settings.py tests/test_conftest_fixture.py
git commit -m "feat: add ollama settings, langchain-ollama dep, and pytest harness"
```

---

### Task 2: Obsidian vault writer

**Files:**
- Create: `memory/vault.py`
- Create: `tests/test_vault.py`
- Modify: `skills/memory_tools.py:23-69`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `vault.daily_note_path(when: date | None = None) -> str`
  - `vault.sanitize_entity_name(name: str) -> str`
  - `vault.entity_note_path(name: str) -> str`
  - `vault.format_capture_line(kind: str, text: str, entity_names: list[str], when: datetime | None = None) -> str`
  - `vault.append_daily_note(line: str, when: date | None = None) -> bool`
  - `vault.ensure_entity_page(name: str, type_: str) -> bool`
  - `vault.put_note(path: str, content: str) -> bool`
  - `vault.get_note(path: str) -> str | None`

- [ ] **Step 1: Write the failing formatting tests**

These four functions are pure — no HTTP, no clock, no DB — which is why they are the only part of the vault layer worth unit testing. Create `tests/test_vault.py`:

```python
from datetime import date, datetime

from memory import vault


def test_daily_note_path_uses_journal_dir_and_iso_date():
    assert vault.daily_note_path(date(2026, 8, 8)) == "Journal/2026-08-08.md"


def test_sanitize_strips_obsidian_reserved_characters():
    assert vault.sanitize_entity_name("Auth [Refactor]") == "Auth Refactor"
    assert vault.sanitize_entity_name("api/v2") == "api-v2"
    assert vault.sanitize_entity_name("a:b|c#d^e") == "abcde"


def test_sanitize_collapses_whitespace_and_trims():
    assert vault.sanitize_entity_name("  Auth   Refactor  ") == "Auth Refactor"


def test_entity_note_path_uses_sanitized_name():
    assert vault.entity_note_path("Auth [Refactor]") == "Entities/Auth Refactor.md"


def test_format_capture_line_renders_time_kind_text_and_links():
    line = vault.format_capture_line(
        "commitment",
        "Finish the auth refactor by Tuesday",
        ["Auth Refactor"],
        when=datetime(2026, 8, 8, 14, 32),
    )
    assert line == "- 14:32 [commitment] Finish the auth refactor by Tuesday [[Auth Refactor]]"


def test_format_capture_line_with_no_entities_has_no_trailing_space():
    line = vault.format_capture_line(
        "fact", "Coffee is good", [], when=datetime(2026, 8, 8, 9, 5)
    )
    assert line == "- 09:05 [fact] Coffee is good"


def test_format_capture_line_links_every_entity():
    line = vault.format_capture_line(
        "idea", "Pair them up", ["Ravi", "Auth Refactor"], when=datetime(2026, 8, 8, 9, 5)
    )
    assert line.endswith("[[Ravi]] [[Auth Refactor]]")


def test_format_capture_line_flattens_newlines_in_text():
    line = vault.format_capture_line(
        "fact", "line one\nline two", [], when=datetime(2026, 8, 8, 9, 5)
    )
    assert line == "- 09:05 [fact] line one line two"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_vault.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'memory.vault'`.

- [ ] **Step 3: Implement memory/vault.py**

Note the verb semantics of the Obsidian Local REST API: `POST` appends to a file, `PUT` replaces it, `GET` returns 404 when absent. `append_daily_note` depends on POST-appends; do not substitute PUT.

Create `memory/vault.py`:

```python
# memory/vault.py
"""Obsidian Local REST API writer.

Verb semantics matter here:
  POST /vault/{path}  appends to the file (creates it if missing)
  PUT  /vault/{path}  replaces the file contents
  GET  /vault/{path}  404s when the file does not exist
"""
import os
import re
import urllib.parse
from datetime import date, datetime

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

OBSIDIAN_API_KEY = os.getenv("OBSIDIAN_API_KEY")
OBSIDIAN_URL = os.getenv("OBSIDIAN_URL", "https://127.0.0.1:27124").rstrip("/")

HEADERS = {
    "Authorization": f"Bearer {OBSIDIAN_API_KEY}",
    "Content-Type": "text/markdown",
}

DAILY_DIR = "Journal"
ENTITY_DIR = "Entities"
TIMEOUT = 5

# Characters Obsidian treats as structural in filenames or wikilinks.
_RESERVED = re.compile(r"[\[\]:|#^]")


def _url(path: str) -> str:
    return f"{OBSIDIAN_URL}/vault/{urllib.parse.quote(path)}"


# --- pure helpers -----------------------------------------------------------

def daily_note_path(when: date = None) -> str:
    return f"{DAILY_DIR}/{(when or date.today()).isoformat()}.md"


def sanitize_entity_name(name: str) -> str:
    """Make a name safe as both a filename and a wikilink target."""
    cleaned = _RESERVED.sub("", name)
    cleaned = cleaned.replace("/", "-").replace("\\", "-")
    return re.sub(r"\s+", " ", cleaned).strip()


def entity_note_path(name: str) -> str:
    return f"{ENTITY_DIR}/{sanitize_entity_name(name)}.md"


def format_capture_line(kind: str, text: str, entity_names: list, when: datetime = None) -> str:
    stamp = (when or datetime.now()).strftime("%H:%M")
    flat = re.sub(r"\s+", " ", text).strip()
    line = f"- {stamp} [{kind}] {flat}"
    links = " ".join(f"[[{sanitize_entity_name(n)}]]" for n in entity_names if sanitize_entity_name(n))
    return f"{line} {links}" if links else line


# --- REST calls -------------------------------------------------------------

def put_note(path: str, content: str) -> bool:
    """Replace a note's contents. Returns True on success."""
    response = requests.put(_url(path), headers=HEADERS, data=content.encode("utf-8"),
                            verify=False, timeout=TIMEOUT)
    return response.status_code in (200, 201, 204)


def get_note(path: str) -> str:
    """Return note contents, or None if absent or unreachable."""
    try:
        response = requests.get(_url(path), headers=HEADERS, verify=False, timeout=TIMEOUT)
    except Exception:
        return None
    return response.text if response.status_code == 200 else None


def append_daily_note(line: str, when: date = None) -> bool:
    """Append one line to today's daily note, creating it if needed."""
    path = daily_note_path(when)
    response = requests.post(_url(path), headers=HEADERS, data=f"{line}\n".encode("utf-8"),
                             verify=False, timeout=TIMEOUT)
    return response.status_code in (200, 201, 204)


def ensure_entity_page(name: str, type_: str) -> bool:
    """Create Entities/<Name>.md if it does not already exist. No-op if present."""
    path = entity_note_path(name)
    if get_note(path) is not None:
        return True
    safe = sanitize_entity_name(name)
    content = (
        "---\n"
        f"type: {type_}\n"
        f"created: {date.today().isoformat()}\n"
        "---\n\n"
        f"# {safe}\n\n"
        "Mentions of this entity appear in the Backlinks pane.\n"
    )
    return put_note(path, content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_vault.py -v`
Expected: 8 passed.

- [ ] **Step 5: Delegate memory_tools HTTP to the vault module**

`skills/memory_tools.py` currently builds Obsidian URLs and headers itself. Route it through `vault` so there is one implementation. Behavior must not change.

Replace the import/config block at the top of `skills/memory_tools.py` (the lines from `import requests` through the `HEADERS = {...}` block, i.e. lines 2-21) with:

```python
import os
from langchain_core.tools import tool
from memory import store
from memory import vault
from memory import vector_store
```

Replace the body of `save_memory` (keeping the `@tool` decorator and docstring) with:

```python
@tool
def save_memory(filename: str, content: str) -> str:
    """Saves a new memory, note, preference, or idea to the Obsidian vault."""
    clean_name = filename.replace(".md", "").strip() + ".md"

    try:
        ok = vault.put_note(clean_name, content)
        result = (f"Successfully saved memory to {clean_name}" if ok
                  else f"Failed to save {clean_name} to Obsidian")
    except Exception as e:
        result = f"Error connecting to Obsidian: {str(e)}"

    try:
        memory_id = store.add_memory(kind="semantic", content=content, title=clean_name,
                                     obsidian_path=clean_name)
        vector_store.index_memory(memory_id, content)
    except Exception as e:
        print(f"[memory_tools] local index write failed: {e}")

    return result
```

Replace the body of `read_memory` with:

```python
@tool
def read_memory(filename: str) -> str:
    """Reads a specific memory or note from the Obsidian vault."""
    clean_name = filename.replace(".md", "").strip() + ".md"

    content = vault.get_note(clean_name)
    if content is not None:
        return content

    try:
        memory = store.find_memory_by_obsidian_path(clean_name)
        if memory:
            return memory["content"]
    except Exception as e:
        return f"Error reading local memory index: {str(e)}"

    return f"Memory '{clean_name}' not found in Obsidian or the local index."
```

- [ ] **Step 6: Verify memory_tools still imports cleanly**

Run: `uv run python -c "from skills.memory_tools import save_memory, read_memory; print(save_memory.name, read_memory.name)"`
Expected: `save_memory read_memory`

- [ ] **Step 7: Commit**

```bash
git add memory/vault.py tests/test_vault.py skills/memory_tools.py
git commit -m "feat: add Obsidian vault writer with daily notes and entity pages"
```

---

### Task 3: Local embeddings and reindex migration

**Files:**
- Modify: `memory/vector_store.py:1-33,36-44`
- Create: `scripts/reindex_embeddings.py`
- Create: `tests/test_vector_store.py`

**Interfaces:**
- Consumes: `config.settings.EMBED_MODEL`, `config.settings.OLLAMA_HOST` (Task 1); the `temp_db` fixture (Task 1).
- Produces: `vector_store.EMBEDDING_MODEL: str`, `vector_store.embed_text(text: str) -> np.ndarray`, `vector_store.index_memory(memory_id: int, text: str) -> None`, `vector_store.search(query: str, top_k: int = 5, kind: str = None) -> list[dict]` — unchanged signatures, now filtering by embedding model.

- [ ] **Step 1: Write the failing tests**

`embed_text` is monkeypatched in every test so the suite never needs Ollama running. Create `tests/test_vector_store.py`:

```python
import numpy as np

from memory import vector_store


def _stub_embedder(monkeypatch, mapping):
    """Make embed_text deterministic: exact text lookup, else a zero-ish default."""
    def fake(text):
        return np.array(mapping.get(text, [0.0, 0.0, 1.0]), dtype=np.float32)
    monkeypatch.setattr(vector_store, "embed_text", fake)


def test_search_returns_closest_match_first(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {
        "cats": [1.0, 0.0, 0.0],
        "kittens": [0.9, 0.1, 0.0],
        "trucks": [0.0, 1.0, 0.0],
    })
    cat_id = temp_db.add_memory(kind="semantic", content="cats")
    truck_id = temp_db.add_memory(kind="semantic", content="trucks")
    vector_store.index_memory(cat_id, "cats")
    vector_store.index_memory(truck_id, "trucks")

    results = vector_store.search("kittens", top_k=2)

    assert results[0]["id"] == cat_id


def test_search_ignores_rows_from_a_different_embedding_model(temp_db, monkeypatch):
    """A half-finished migration must degrade to fewer results, not crash."""
    _stub_embedder(monkeypatch, {"cats": [1.0, 0.0, 0.0]})
    memory_id = temp_db.add_memory(kind="semantic", content="cats")
    vector_store.index_memory(memory_id, "cats")

    conn = temp_db._get_conn()
    conn.execute("UPDATE embeddings SET model = ? WHERE memory_id = ?",
                 ("models/gemini-embedding-001", memory_id))
    conn.commit()

    assert vector_store.search("cats") == []


def test_search_on_empty_index_returns_empty_list(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {})
    assert vector_store.search("anything") == []


def test_index_memory_records_the_active_model_and_dim(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {"cats": [1.0, 0.0, 0.0]})
    memory_id = temp_db.add_memory(kind="semantic", content="cats")
    vector_store.index_memory(memory_id, "cats")

    row = temp_db._get_conn().execute(
        "SELECT model, dim FROM embeddings WHERE memory_id = ?", (memory_id,)
    ).fetchone()
    assert row["model"] == vector_store.EMBEDDING_MODEL
    assert row["dim"] == 3


def test_search_filters_by_kind(temp_db, monkeypatch):
    _stub_embedder(monkeypatch, {
        "cats": [1.0, 0.0, 0.0],
        "a decision": [0.99, 0.0, 0.0],
    })
    cat_id = temp_db.add_memory(kind="semantic", content="cats")
    dec_id = temp_db.add_memory(kind="decision", content="a decision")
    vector_store.index_memory(cat_id, "cats")
    vector_store.index_memory(dec_id, "a decision")

    results = vector_store.search("cats", kind="decision")

    assert [r["id"] for r in results] == [dec_id]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_vector_store.py -v`
Expected: `test_search_ignores_rows_from_a_different_embedding_model` FAILS (the model filter does not exist yet) and `test_index_memory_records_the_active_model_and_dim` FAILS (`assert 'models/gemini-embedding-001' == 'nomic-embed-text'`).

- [ ] **Step 3: Swap the embedder to Ollama**

In `memory/vector_store.py`, replace lines 1-16 (the imports through `_get_embedder`) with:

```python
import numpy as np
from datetime import datetime
from langchain_ollama import OllamaEmbeddings
from config.settings import EMBED_MODEL, OLLAMA_HOST
from memory import store

EMBEDDING_MODEL = EMBED_MODEL

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_HOST)
    return _embedder
```

- [ ] **Step 4: Add the model filter to search()**

In `memory/vector_store.py`, replace the `rows = conn.execute(...)` call at the top of `search()` with:

```python
    rows = conn.execute(
        "SELECT e.memory_id, e.vector, e.dim FROM embeddings e WHERE e.model = ?",
        (EMBEDDING_MODEL,),
    ).fetchall()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_vector_store.py -v`
Expected: 5 passed.

- [ ] **Step 6: Write the reindex migration script**

Create `scripts/reindex_embeddings.py`:

```python
"""One-shot migration: re-embed every memory with the active local model.

gemini-embedding-001 produced 3072-dim vectors; nomic-embed-text produces 768.
Mixing dimensions in one table breaks cosine search, so every row is rewritten.
Safe to re-run.
"""
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory import store, vector_store  # noqa: E402


def main():
    conn = store._get_conn()

    backup = f"{store.DB_PATH}.bak-{date.today().strftime('%Y%m%d')}"
    shutil.copyfile(store.DB_PATH, backup)
    print(f"[*] Backed up database to {backup}")

    rows = conn.execute("SELECT id, content FROM memories ORDER BY id").fetchall()
    print(f"[*] Re-embedding {len(rows)} memories with {vector_store.EMBEDDING_MODEL}...")

    done, failed = 0, 0
    for row in rows:
        try:
            vector_store.index_memory(row["id"], row["content"])
            done += 1
        except Exception as e:
            failed += 1
            print(f"    ! memory {row['id']} failed: {e}")

    conn.execute("DELETE FROM embeddings WHERE model != ?", (vector_store.EMBEDDING_MODEL,))
    conn.commit()

    print(f"[*] Done. {done} re-embedded, {failed} failed, stale rows purged.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the migration against the real database**

Ollama must be running.

```powershell
uv run python scripts/reindex_embeddings.py
```

Expected: a `[*] Backed up database to ...bak-20260808` line, then `[*] Done. N re-embedded, 0 failed, stale rows purged.`

Confirm no rows survive under the old model:

```powershell
uv run python -c "from memory import store; print(store._get_conn().execute('SELECT model, COUNT(*) FROM embeddings GROUP BY model').fetchall()[:])"
```

Expected: only `nomic-embed-text` appears.

- [ ] **Step 8: Verify semantic search still works end to end**

```powershell
uv run python -c "from skills.memory_tools import search_memory; print(search_memory.invoke({'query': 'project'}))"
```

Expected: either matching memories, or `I couldn't find any memories matching that.` — but **not** a traceback.

- [ ] **Step 9: Commit**

```bash
git add memory/vector_store.py scripts/reindex_embeddings.py tests/test_vector_store.py
git commit -m "feat: move embeddings to local nomic-embed-text with reindex migration"
```

---

### Task 4: Hermes client and capture JSON parsing

**Files:**
- Create: `llm/hermes.py`
- Create: `tests/test_hermes.py`

**Interfaces:**
- Consumes: `config.settings.HERMES_MODEL`, `OLLAMA_HOST` (Task 1); the eight tier-1 tools from `skills/memory_tools.py` and `skills/system_tools.py` (existing).
- Produces:
  - `hermes.HERMES_TOOLS: list` — exactly 8 LangChain tools
  - `hermes.escalate_to_gemini` — a `@tool` taking `reason: str`
  - `hermes.parse_capture(raw: str) -> dict | None` — pure, normalizes and validates one JSON payload
  - `hermes.ask_hermes(text: str) -> dict` — `{"reply": str, "escalate": bool, "reason": str}`
  - `hermes.extract_capture(user_text: str, reply: str) -> dict | None`
  - `hermes.CAPTURE_KINDS: set[str]`

- [ ] **Step 1: Write the failing parser tests**

`parse_capture` is the one piece of Hermes handling worth heavy testing — it is pure, and it is where a small model's sloppiness actually lands. Create `tests/test_hermes.py`:

```python
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


def test_hermes_tier_holds_exactly_eight_tools():
    assert len(hermes.HERMES_TOOLS) == 8
    assert "escalate_to_gemini" in {t.name for t in hermes.HERMES_TOOLS}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hermes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.hermes'`.

- [ ] **Step 3: Implement llm/hermes.py**

Create `llm/hermes.py`:

```python
# llm/hermes.py
"""Local Hermes 3 brain, served by Ollama.

Hermes handles the common case with a deliberately small tool surface. Small
models degrade sharply past ~10 bound tools, so HERMES_TOOLS stays at 8. When
Hermes decides a request is beyond it, it calls escalate_to_gemini and the
router hands the original text to the full 26-tool Gemini loop.
"""
import json
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

from config.settings import HERMES_MODEL, OLLAMA_HOST
from skills.memory_tools import (
    get_recent_memories, recall_preference, remember_fact, search_memory,
)
from skills.system_tools import open_website, play_on_youtube, shutdown_system

CAPTURE_KINDS = {"fact", "commitment", "decision", "idea", "preference"}
ENTITY_TYPES = {"project", "person", "topic"}

MAX_TOOL_HOPS = 3
REQUEST_TIMEOUT = 30
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@tool
def escalate_to_gemini(reason: str) -> str:
    """Hand this request to the more capable cloud assistant.

    Call this when the request needs multi-step reasoning, the screen, the
    calendar, GitHub, the weather, the news, project management, or any tool
    you have not been given. Give a one-line reason."""
    return f"Escalating: {reason}"


HERMES_TOOLS = [
    search_memory,
    remember_fact,
    recall_preference,
    get_recent_memories,
    open_website,
    play_on_youtube,
    shutdown_system,
    escalate_to_gemini,
]

_TOOL_MAP = {t.name: t for t in HERMES_TOOLS}

HERMES_SYSTEM_PROMPT = """You are Jarvis, a local voice assistant. Answer in at most two short
conversational sentences, as speech, never as markdown.

You have a small set of tools. Use them when they fit the request.

If the request needs anything you do NOT have a tool for -- the user's screen, calendar,
GitHub, weather, news, projects or tasks, saving a full note, or reasoning that takes
several steps -- call escalate_to_gemini immediately with a one-line reason. Do not guess
or apologise; escalating is the correct move, not a failure."""

CAPTURE_PROMPT = """You extract things worth remembering from a conversation.

Reply with ONE JSON object and nothing else. No prose, no code fences.

{{"capture": bool, "kind": str, "text": str, "entities": [{{"name": str, "type": str}}], "due_date": str or null}}

- capture: true only if something durable was stated -- a fact about the user, a commitment,
  a decision, an idea, or a preference. Small talk, greetings, and answers to questions the
  user asked are NOT captures. When unsure, use false.
- kind: one of fact, commitment, decision, idea, preference.
- text: one self-contained sentence, written in the third person about the user.
- entities: people, projects or topics named. type is one of project, person, topic.
  Use [] if none.
- due_date: ISO YYYY-MM-DD if a deadline was stated, else null. Today is {today}.

Conversation:
User: {user_text}
Jarvis: {reply}"""

_llm = None
_llm_with_tools = None


def _get_llm():
    global _llm, _llm_with_tools
    if _llm is None:
        _llm = ChatOllama(model=HERMES_MODEL, base_url=OLLAMA_HOST,
                          temperature=0.4, client_kwargs={"timeout": REQUEST_TIMEOUT})
        _llm_with_tools = _llm.bind_tools(HERMES_TOOLS)
    return _llm, _llm_with_tools


def is_available() -> bool:
    """True if the Ollama server answers. Used to skip Hermes without raising."""
    import requests
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


def parse_capture(raw: str):
    """Normalize one capture payload from Hermes. Returns None if there is nothing to store.

    Small models wrap JSON in prose or fences, emit bare strings where objects were asked
    for, and invent kinds. Every one of those is normalized or rejected here rather than
    downstream.
    """
    if not raw:
        return None

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("capture") is not True:
        return None

    kind = payload.get("kind")
    if kind not in CAPTURE_KINDS:
        return None

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    entities = []
    for raw_entity in payload.get("entities") or []:
        if isinstance(raw_entity, str):
            name, type_ = raw_entity, "topic"
        elif isinstance(raw_entity, dict):
            name, type_ = raw_entity.get("name"), raw_entity.get("type")
        else:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        entities.append({
            "name": name.strip(),
            "type": type_ if type_ in ENTITY_TYPES else "topic",
        })

    due_date = payload.get("due_date")
    if not (isinstance(due_date, str) and _ISO_DATE.match(due_date)):
        due_date = None

    return {"kind": kind, "text": text.strip(), "entities": entities, "due_date": due_date}


def ask_hermes(text: str) -> dict:
    """Run one Hermes turn. Raises on transport failure so the router can escalate."""
    _, llm_with_tools = _get_llm()
    prompt = HERMES_SYSTEM_PROMPT + f"\nToday's date is {date.today().isoformat()}."
    messages = [SystemMessage(content=prompt), HumanMessage(content=text)]

    final = None
    for _ in range(MAX_TOOL_HOPS):
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        final = response

        if not response.tool_calls:
            break

        for call in response.tool_calls:
            if call["name"] == "escalate_to_gemini":
                return {"reply": "", "escalate": True,
                        "reason": call["args"].get("reason", "unspecified")}

            tool_fn = _TOOL_MAP.get(call["name"])
            if tool_fn is None:
                result = f"Unknown tool: {call['name']}"
            else:
                try:
                    result = tool_fn.invoke(call["args"])
                except Exception as e:
                    result = f"Tool '{call['name']}' failed: {e}"
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

            if call["name"] == "shutdown_system":
                import os
                print("[*] Terminating V.A.U.L.T. OS...")
                os._exit(0)

    reply = final.content if final is not None else ""
    if isinstance(reply, list):
        reply = " ".join(b.get("text", "") for b in reply if isinstance(b, dict)).strip()
    reply = str(reply).strip()

    if not reply:
        return {"reply": "", "escalate": True, "reason": "hermes produced no reply"}
    return {"reply": reply, "escalate": False, "reason": ""}


def extract_capture(user_text: str, reply: str):
    """Ask Hermes what, if anything, from this exchange is worth keeping."""
    llm, _ = _get_llm()
    prompt = CAPTURE_PROMPT.format(today=date.today().isoformat(),
                                   user_text=user_text, reply=reply)
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return parse_capture(str(content))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hermes.py -v`
Expected: 16 passed.

- [ ] **Step 5: Smoke-test Hermes against the live model**

Ollama must be running. This is a manual check, not a test — model output is not deterministic.

```powershell
uv run python -c "from llm import hermes; print(hermes.is_available()); print(hermes.ask_hermes('what is two plus two'))"
```

Expected: `True`, then a dict with `escalate: False` and a short spoken-style reply.

```powershell
uv run python -c "from llm import hermes; print(hermes.ask_hermes('what is on my calendar tomorrow'))"
```

Expected: `escalate: True` with a reason mentioning the calendar. If Hermes answers instead of escalating, sharpen the escalation paragraph in `HERMES_SYSTEM_PROMPT` and retry — this is the prompt-tuning loop the spec anticipated.

- [ ] **Step 6: Commit**

```bash
git add llm/hermes.py tests/test_hermes.py
git commit -m "feat: add local Hermes client with 8-tool tier and capture extraction"
```

---

### Task 5: Capture pipeline

**Files:**
- Create: `memory/capture.py`
- Create: `tests/test_capture.py`

**Interfaces:**
- Consumes: `hermes.extract_capture` (Task 4); `vault.append_daily_note`, `vault.ensure_entity_page`, `vault.format_capture_line` (Task 2); `vector_store.index_memory` (Task 3); `settings.ENABLE_AUTO_CAPTURE` (Task 1); existing `store.get_or_create_entity`, `store.add_memory`, `store.add_relationship`, `store.add_task`.
- Produces:
  - `capture.persist_capture(payload: dict, source_text: str) -> int | None` — returns the new memory id
  - `capture.enqueue(user_text: str, reply: str) -> None` — non-blocking
  - `capture.set_listener(fn) -> None` — registers a `fn(payload: dict) -> None` callback fired after a successful capture, used by the GUI

- [ ] **Step 1: Write the failing tests**

These cover the exact store-API relationships the spec self-review corrected: entity identity is `(type, name)`, the memory-to-entity link is `add_memory(entity_id=...)`, and `relationships` rows only exist for co-occurring entities. Create `tests/test_capture.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'memory.capture'`.

- [ ] **Step 3: Implement memory/capture.py**

Create `memory/capture.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capture.py -v`
Expected: 14 passed.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -v`
Expected: 47 passed.

- [ ] **Step 6: Commit**

```bash
git add memory/capture.py tests/test_capture.py
git commit -m "feat: add background capture pipeline writing to SQLite and vault"
```

---

### Task 6: Router

**Files:**
- Create: `llm/router.py`
- Create: `tests/test_router.py`

**Interfaces:**
- Consumes: `hermes.ask_hermes` (Task 4); existing `llm.gemini.ask_gemini`.
- Produces: `router.handle(text: str) -> tuple[str, str]` where the second element is `"LOCAL"` or `"CLOUD"`.

- [ ] **Step 1: Write the failing tests**

Both brains are mocked; this task tests routing decisions, not model quality.

One import-time caveat: `llm/router.py` does `from llm.gemini import ask_gemini`, and `llm/gemini.py` constructs a `ChatGoogleGenerativeAI` client and binds 26 tools at module import. So importing the router requires `GOOGLE_API_KEY` to be present in `.env` — it must be, or the app does not run at all. No network call happens at import, only client construction, so the tests stay offline.

Create `tests/test_router.py`:

```python
import pytest

from llm import router


@pytest.fixture(autouse=True)
def stub_gemini(monkeypatch):
    monkeypatch.setattr(router, "ask_gemini", lambda text: f"gemini: {text}")


def test_local_answer_is_returned_without_touching_gemini(monkeypatch):
    monkeypatch.setattr(router.hermes, "ask_hermes",
                        lambda text: {"reply": "four", "escalate": False, "reason": ""})
    assert router.handle("two plus two") == ("four", "LOCAL")


def test_escalation_delegates_the_original_text_to_gemini(monkeypatch):
    monkeypatch.setattr(router.hermes, "ask_hermes",
                        lambda text: {"reply": "", "escalate": True, "reason": "needs calendar"})
    assert router.handle("what is on my calendar") == ("gemini: what is on my calendar", "CLOUD")


def test_hermes_exception_falls_back_to_gemini(monkeypatch):
    def boom(text):
        raise ConnectionError("Ollama refused the connection")
    monkeypatch.setattr(router.hermes, "ask_hermes", boom)
    assert router.handle("hello") == ("gemini: hello", "CLOUD")


def test_empty_hermes_reply_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(router.hermes, "ask_hermes",
                        lambda text: {"reply": "   ", "escalate": False, "reason": ""})
    assert router.handle("hello") == ("gemini: hello", "CLOUD")


def test_gemini_failure_after_escalation_returns_a_spoken_error(monkeypatch):
    monkeypatch.setattr(router.hermes, "ask_hermes",
                        lambda text: {"reply": "", "escalate": True, "reason": "x"})
    def boom(text):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(router, "ask_gemini", boom)

    reply, brain = router.handle("hello")

    assert brain == "CLOUD"
    assert "rate limiting" in reply.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.router'`.

- [ ] **Step 3: Implement llm/router.py**

Create `llm/router.py`:

```python
# llm/router.py
"""Hermes-first routing with escalation to Gemini.

Escalation discards the Hermes attempt entirely and hands Gemini the ORIGINAL
user text, so ask_gemini's own conversation history and multi-hop loop stay
coherent. The two brains never share partial state.
"""
from llm import hermes
from llm.gemini import ask_gemini

RATE_LIMIT_REPLY = ("Boss, Google is rate limiting my API. Give me a moment to cool down.")
GENERIC_ERROR_REPLY = "I hit an error in my cognitive engine."


def handle(text: str):
    """Answer one turn. Returns (reply, brain) with brain in {'LOCAL', 'CLOUD'}."""
    try:
        result = hermes.ask_hermes(text)
        if not result["escalate"] and result["reply"].strip():
            return result["reply"], "LOCAL"
        if result["escalate"]:
            print(f"[router] escalating: {result['reason']}")
    except Exception as e:
        print(f"[router] hermes unavailable, escalating: {e}")

    try:
        return ask_gemini(text), "CLOUD"
    except Exception as e:
        message = str(e)
        if "429" in message or "RESOURCE_EXHAUSTED" in message:
            return RATE_LIMIT_REPLY, "CLOUD"
        print(f"[router] gemini failed: {e}")
        return GENERIC_ERROR_REPLY, "CLOUD"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_router.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add llm/router.py tests/test_router.py
git commit -m "feat: add Hermes-first router with escalation to Gemini"
```

---

### Task 7: Wake word matching and stripping

**Files:**
- Modify: `voice/wakeword.py:1-4` (replace the whole file)
- Create: `tests/test_wakeword.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `wakeword.WAKE_WORDS: list[str]`, `wakeword.detect_wake_word(text: str) -> bool`, `wakeword.strip_wake_word(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wakeword.py`:

```python
from voice import wakeword


def test_detects_the_canonical_wake_word():
    assert wakeword.detect_wake_word("Jarvis what is the weather") is True


def test_detects_whisper_homophones():
    assert wakeword.detect_wake_word("Travis, open youtube") is True
    assert wakeword.detect_wake_word("garbage save a memory") is True
    assert wakeword.detect_wake_word("Jaress, what time is it") is True


def test_rejects_text_without_a_wake_word():
    assert wakeword.detect_wake_word("what is the weather") is False
    assert wakeword.detect_wake_word("") is False


def test_strips_the_wake_word_and_leading_punctuation():
    assert wakeword.strip_wake_word("Jarvis, what is the weather") == "what is the weather"
    assert wakeword.strip_wake_word("Travis open youtube") == "open youtube"


def test_strips_only_the_first_occurrence():
    assert wakeword.strip_wake_word("Jarvis tell Jarvis hello") == "tell Jarvis hello"


def test_strip_preserves_original_casing_of_the_remainder():
    assert wakeword.strip_wake_word("jarvis Open YouTube") == "Open YouTube"


def test_strip_is_a_noop_without_a_wake_word():
    assert wakeword.strip_wake_word("what is the weather") == "what is the weather"


def test_strip_of_the_bare_wake_word_returns_empty():
    assert wakeword.strip_wake_word("Jarvis") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_wakeword.py -v`
Expected: FAIL with `AttributeError: module 'voice.wakeword' has no attribute 'WAKE_WORDS'`.

- [ ] **Step 3: Replace voice/wakeword.py**

The file currently holds `WAKE_WORD = "hey jarvis"` and is imported by nothing, while `main.py` hardcodes the homophone list inline. Replace the entire file contents with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wakeword.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add voice/wakeword.py tests/test_wakeword.py
git commit -m "feat: make wakeword module the single source of wake-word matching"
```

---

### Task 8: Wire the GUI and voice loop

**Files:**
- Modify: `main.py:112-115` (imports), `main.py:186-190` (vault panel), `main.py:272-294` (event loop)

**Interfaces:**
- Consumes: `router.handle` (Task 6); `capture.enqueue`, `capture.set_listener` (Task 5); `wakeword.detect_wake_word`, `wakeword.strip_wake_word` (Task 7); existing `store.list_memories`.
- Produces: nothing consumed by later tasks — this is the final integration.

This task has no unit tests. Mocking Whisper, Kokoro and Tkinter would test the mocks rather than the system, so verification is the manual script in Step 6.

- [ ] **Step 1: Update the imports**

In `main.py`, replace the import block at lines 112-115:

```python
from voice.listener import listen
from voice.speaker import speak
from llm.gemini import ask_gemini, jarvis_tools
```

with:

```python
from voice.listener import listen
from voice.speaker import speak
from voice.wakeword import detect_wake_word, strip_wake_word
from llm.gemini import jarvis_tools
from llm.router import handle as route_request
from memory import capture, store
```

Note `ask_gemini` is no longer imported here — the router owns that call now. `jarvis_tools` is still needed by `build_right_panel`.

- [ ] **Step 2: Add the follow-up window constant**

In `main.py`, immediately after the `FONT_TITLE = ...` line, add:

```python
# Seconds after a reply during which speech is accepted without the wake word.
FOLLOW_UP_WINDOW = 15
```

- [ ] **Step 3: Make the vault panel live**

In `main.py`'s `build_left_panel`, replace the two lines that hardcode the fake document list:

```python
        self.docs_list = ctk.CTkLabel(self.left_panel, text="Master Plan.md\nProject Alpha.md\n", font=FONT_MAIN, text_color="#555555", justify="left")
        self.docs_list.pack(anchor="w", padx=10)
```

with:

```python
        self.docs_list = ctk.CTkLabel(self.left_panel, text="(empty)", font=FONT_MAIN,
                                      text_color="#555555", justify="left")
        self.docs_list.pack(anchor="w", padx=10)
        self.refresh_vault_panel()
```

Then add these two methods to `VaultCommandCenter`, immediately after `update_status`:

```python
    def refresh_vault_panel(self):
        """Show the most recent captures. Main thread only."""
        try:
            memories = store.list_memories(limit=5)
        except Exception:
            return
        if not memories:
            self.docs_list.configure(text="(empty)")
            return
        lines = [f"{m['kind']}: {m['content'][:34]}" for m in memories]
        self.docs_list.configure(text="\n".join(lines))

    def on_capture(self, payload):
        """Capture-thread callback. Tkinter is main-thread only, hence after(0, ...)."""
        self.after(0, self.refresh_vault_panel)
        self.after(0, lambda: self.log_to_console("MEMORY", f"[{payload['kind']}] {payload['text']}"))
```

- [ ] **Step 4: Register the capture listener**

In `VaultCommandCenter.__init__`, immediately before the `self.ai_thread = threading.Thread(...)` line, add:

```python
        capture.set_listener(self.on_capture)
```

- [ ] **Step 5: Replace the event loop**

In `main.py`, replace the entire `event_loop` method (lines 272-294) with:

```python
    def event_loop(self):
        time.sleep(2)
        follow_up_until = 0.0

        while self.ai_active:
            self.update_status("PRIMARY DIRECTIVE . IDLE", "AWAITING AUDIO", TEXT_COLOR)

            text = listen()
            if not text:
                continue

            self.log_to_console("USER", text)

            in_follow_up = time.monotonic() < follow_up_until
            if not (detect_wake_word(text) or in_follow_up):
                continue

            request = strip_wake_word(text) if detect_wake_word(text) else text
            if not request:
                continue

            self.update_status("PRIMARY DIRECTIVE . ACTIVE", "PROCESSING", "#FFA500")
            try:
                reply, brain = route_request(request)
            except Exception as e:
                self.log_to_console("SYS_ERROR", str(e))
                speak("I encountered a critical error in my cognitive engine.")
                continue

            self.log_to_console("JARVIS", reply)
            self.update_status(f"PRIMARY DIRECTIVE . {brain}", "TRANSMITTING", ACCENT_COLOR)
            speak(reply)

            capture.enqueue(request, reply)
            follow_up_until = time.monotonic() + FOLLOW_UP_WINDOW
```

- [ ] **Step 6: Verify the full suite still passes**

Run: `uv run pytest tests/ -v`
Expected: 60 passed.

- [ ] **Step 7: Manual end-to-end verification**

Start Ollama and Obsidian (with the Local REST API plugin enabled), then:

```powershell
uv run main.py
```

Walk the spec's acceptance criteria in order and confirm each:

1. Say **"Jarvis, what do you remember about me?"** → the status line reads `PRIMARY DIRECTIVE . LOCAL` and the console shows a reply.
2. Stop Ollama (`Get-Process ollama | Stop-Process`), say **"Jarvis, what's on my calendar tomorrow?"** → status reads `PRIMARY DIRECTIVE . CLOUD` and it still answers. Restart Ollama afterwards.
3. Say **"Jarvis, I'll finish the auth refactor by Tuesday."** Within ~15s of the reply, confirm all of:
   - a `MEMORY> [commitment] ...` line appears in the console and the DOCUMENTS panel updates
   - `Journal/2026-08-08.md` in the vault has a new `- HH:MM [commitment] ... [[Auth Refactor]]` line
   - `Entities/Auth Refactor.md` exists
   - `uv run python -c "from memory import store; print(store.list_overdue_tasks(as_of='2026-08-12'))"` lists the task
4. Say **"Jarvis, Ravi is reviewing the auth refactor."** then check the co-occurrence edge exists:
   `uv run python -c "from memory import store; print(store._get_conn().execute('SELECT * FROM relationships').fetchall()[:])"`
   Expected: at least one `mentioned_with` row.
5. Immediately after a reply, say **"and what about Wednesday?"** with no wake word → it is accepted and answered.

- [ ] **Step 8: Commit**

```bash
git add main.py
git commit -m "feat: route through Hermes, add follow-up window and live vault panel"
```

---

## Post-Implementation

- [ ] **Update CLAUDE.md**

`CLAUDE.md` describes `ask_gemini` as the orchestration entry point and states that Gemini is the only cloud call besides vision. Both are now stale. Update the Architecture section to describe the router, the two tool tiers, the capture pipeline, and the local embedder; add `ollama pull` to the runtime requirements; note that `voice/wakeword.py` is now live rather than unused.

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Hermes routing and auto-capture"
```

- [ ] **Verify the branch is clean**

Run: `git status --short`
Expected: only the pre-existing unrelated modifications from before this work started. No files listed in this plan should be uncommitted.
