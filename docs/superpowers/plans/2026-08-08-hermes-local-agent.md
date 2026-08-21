# Hermes Local Agent + Obsidian Second Brain Implementation Plan

> **SUPERSEDED.** The escalation design described below (a router calling Hermes
> first, with an `escalate_to_gemini` tool for out-of-tier requests) was reversed
> after benchmarking: only 1 of 6 requests that needed Gemini actually escalated,
> and the rest invented plausible-but-wrong tool calls with real side effects. Hermes
> shipped as capture-only instead — all conversation goes to Gemini via
> `llm/gemini.py::ask_gemini` (see `llm/router.py`, `llm/hermes.py`'s module
> docstring). The corrections are noted further down in this document; this banner
> exists so they aren't missed. Kept as a historical record, not rewritten.

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
  - `vault.put_note(path: str, content: str) -> requests.Response` (raw response, so a caller can build a diagnostic message from `response.status_code` / `response.text` on failure)
  - `vault.get_note(path: str) -> str | None`

- [ ] **Step 1: Write the failing formatting tests**

These four functions are pure — no HTTP, no clock, no DB — which is why they are the only part of the vault layer worth unit testing. The REST functions get their own regression coverage below: this project is Windows-only, so `sanitize_entity_name` must also handle the Windows-illegal characters `< > " ? *` (not just Obsidian's structural characters), and the POST-vs-PUT verb distinction in `append_daily_note` vs `put_note` is pinned with mocked `requests` calls, because a PUT there would silently destroy a whole day's accumulated notes. Create `tests/test_vault.py`:

```python
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from memory import vault


def _mock_response(status_code=200, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def test_daily_note_path_uses_journal_dir_and_iso_date():
    assert vault.daily_note_path(date(2026, 8, 8)) == "Journal/2026-08-08.md"


def test_sanitize_strips_obsidian_reserved_characters():
    assert vault.sanitize_entity_name("Auth [Refactor]") == "Auth Refactor"
    assert vault.sanitize_entity_name("api/v2") == "api-v2"
    assert vault.sanitize_entity_name("a:b|c#d^e") == "abcde"


def test_sanitize_collapses_whitespace_and_trims():
    assert vault.sanitize_entity_name("  Auth   Refactor  ") == "Auth Refactor"


def test_sanitize_strips_remaining_windows_illegal_characters():
    assert vault.sanitize_entity_name("What?") == "What"
    assert vault.sanitize_entity_name('"quoted"') == "quoted"
    assert vault.sanitize_entity_name("<tag>") == "tag"
    assert vault.sanitize_entity_name("a*b") == "ab"
    assert vault.sanitize_entity_name('<>:"/\\|?*') == "--"


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


# --- REST verb regression tests ---------------------------------------------
#
# A PUT in append_daily_note would silently replace (destroy) a whole day's
# accumulated notes where POST appends. These tests pin the verb, and the
# path/URL each call targets, so that regression can't sneak back in.

def test_put_note_issues_a_put_to_the_correct_url():
    with patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_put.return_value = _mock_response(200)

        vault.put_note("Journal/2026-08-08.md", "content")

        mock_put.assert_called_once()
        mock_post.assert_not_called()
        called_url = mock_put.call_args.args[0]
        assert called_url == vault._url("Journal/2026-08-08.md")


def test_put_note_returns_the_response_for_diagnostics():
    with patch("memory.vault.requests.put") as mock_put:
        mock_put.return_value = _mock_response(500, "Internal Server Error")

        response = vault.put_note("x.md", "content")

        assert response.status_code == 500
        assert response.text == "Internal Server Error"


def test_append_daily_note_issues_a_post_not_a_put():
    with patch("memory.vault.requests.post") as mock_post, \
         patch("memory.vault.requests.put") as mock_put:
        mock_post.return_value = _mock_response(200)

        vault.append_daily_note("- 09:00 [fact] hi", when=date(2026, 8, 8))

        mock_post.assert_called_once()
        mock_put.assert_not_called()
        called_url = mock_post.call_args.args[0]
        assert called_url == vault._url("Journal/2026-08-08.md")


def test_ensure_entity_page_creates_via_put_and_never_posts_when_absent():
    with patch("memory.vault.requests.get") as mock_get, \
         patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_get.return_value = _mock_response(404)
        mock_put.return_value = _mock_response(201)

        vault.ensure_entity_page("Ravi", "person")

        mock_put.assert_called_once()
        mock_post.assert_not_called()
        called_url = mock_put.call_args.args[0]
        assert called_url == vault._url("Entities/Ravi.md")


def test_ensure_entity_page_is_a_noop_when_the_page_already_exists():
    with patch("memory.vault.requests.get") as mock_get, \
         patch("memory.vault.requests.put") as mock_put, \
         patch("memory.vault.requests.post") as mock_post:
        mock_get.return_value = _mock_response(200, "already here")

        result = vault.ensure_entity_page("Ravi", "person")

        assert result is True
        mock_put.assert_not_called()
        mock_post.assert_not_called()
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

# Characters Obsidian treats as structural in filenames or wikilinks, plus the
# remaining characters Windows forbids in filenames (this project is Windows-only
# and entity names may be produced by an LLM, so `<>"?*` are realistic inputs).
_RESERVED = re.compile(r'[\[\]:|#^<>"?*]')


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

def _ok(response) -> bool:
    return response.status_code in (200, 201, 204)


def put_note(path: str, content: str) -> requests.Response:
    """Replace a note's contents. Returns the raw response so callers can
    check success via `_ok(response)` and, on failure, reconstruct a
    diagnostic message from `response.status_code` / `response.text`."""
    response = requests.put(_url(path), headers=HEADERS, data=content.encode("utf-8"),
                            verify=False, timeout=TIMEOUT)
    return response


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
    return _ok(response)


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
    return _ok(put_note(path, content))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_vault.py -v`
Expected: 14 passed.

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
        response = vault.put_note(clean_name, content)
        if response.status_code in (200, 201, 204):
            result = f"Successfully saved memory to {clean_name}"
        else:
            result = f"Failed to save: {response.text} (Status Code: {response.status_code})"
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
Expected: 9 passed. (Original 5 plus 4 added in a post-review fix pass covering the migration
script's failure behavior — see Step 6 note below.)

- [ ] **Step 6: Write the reindex migration script**

Create `scripts/reindex_embeddings.py`. Note: the version below is the *shipped* version,
already incorporating a review fix. The first draft purged all stale-model rows
unconditionally after the re-embed loop (`DELETE FROM embeddings WHERE model != ?`), which
is unsafe — if the embedder is down and every row fails, that line still deletes every
surviving old-model embedding while zero new ones were written, destroying data. The fix
scopes the purge to only the `memory_id`s that were *successfully* re-embedded this run, and
gives the operator an unmistakable console message in every outcome (full success, partial
failure, total failure). The backup suffix also gained a time component (not just the date)
so a same-day re-run can never overwrite the true pre-migration snapshot.

```python
"""One-shot migration: re-embed every memory with the active local model.

gemini-embedding-001 produced 3072-dim vectors; nomic-embed-text produces 768.
Mixing dimensions in one table breaks cosine search, so every row is rewritten.

Safe to re-run: the purge of old-model rows is scoped to only the memories
that were *successfully* re-embedded in this run. If the embedder is down
(e.g. Ollama not running) and every row fails, nothing is deleted and the
script can simply be re-run once the embedder is back. If only some rows
fail, the surviving old-model rows for those specific memories are left in
place rather than destroyed, and re-running finishes the job.
"""
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory import store, vector_store  # noqa: E402


def main():
    conn = store._get_conn()

    # Timestamped (not just dated) so a second run on the same day can never
    # overwrite the pre-migration snapshot from an earlier run today. Taken
    # before any mutation.
    backup = f"{store.DB_PATH}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    shutil.copyfile(store.DB_PATH, backup)
    print(f"[*] Backed up database to {backup}")

    rows = conn.execute("SELECT id, content FROM memories ORDER BY id").fetchall()
    print(f"[*] Re-embedding {len(rows)} memories with {vector_store.EMBEDDING_MODEL}...")

    succeeded_ids = []
    failed = 0
    for row in rows:
        try:
            vector_store.index_memory(row["id"], row["content"])
            succeeded_ids.append(row["id"])
        except Exception as e:
            failed += 1
            print(f"    ! memory {row['id']} failed: {e}")

    done = len(succeeded_ids)

    # index_memory() upserts on memory_id, so a memory that was successfully
    # re-embedded already carries the active model on its one and only
    # embeddings row -- this DELETE is a defensive no-op for those rows, not
    # the mechanism that updates them. What it actually protects is memories
    # that FAILED to re-embed: because the scope is succeeded_ids only, their
    # still-stale-model row is never touched, on a partial *or* total
    # failure (succeeded_ids is empty on total failure, so nothing runs).
    if succeeded_ids:
        placeholders = ", ".join("?" for _ in succeeded_ids)
        conn.execute(
            f"DELETE FROM embeddings WHERE model != ? AND memory_id IN ({placeholders})",
            (vector_store.EMBEDDING_MODEL, *succeeded_ids),
        )
        conn.commit()

    if failed and done == 0:
        print(
            f"[!] TOTAL FAILURE: 0 of {len(rows)} memories were re-embedded "
            f"({failed} failed, e.g. Ollama unreachable). NOTHING WAS "
            "PURGED -- all pre-existing embeddings are untouched. Fix the "
            "embedder and re-run this script; it is safe to re-run."
        )
    elif failed:
        print(
            f"[!] PARTIAL FAILURE: {done} re-embedded, {failed} failed. The "
            f"{failed} memories that failed still have their OLD (pre-"
            "migration) embedding in place -- not purged, not replaced. "
            "Fix the embedder and re-run this script to finish the job; it "
            "is safe to re-run."
        )
    else:
        print(f"[*] Done. {done} re-embedded, 0 failed. No stale-model embeddings remain.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the migration against the real database**

Ollama must be running.

```powershell
uv run python scripts/reindex_embeddings.py
```

Expected: a `[*] Backed up database to ...bak-20260808-143022-123456` line, then
`[*] Done. N re-embedded, 0 failed. No stale-model embeddings remain.` If instead you see a
`[!] TOTAL FAILURE` or `[!] PARTIAL FAILURE` line, the old embeddings for whichever memories
failed were deliberately left in place untouched -- fix the embedder (confirm Ollama is
running and `nomic-embed-text` is pulled) and re-run.

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

> **Post-implementation note (2026-08-22): scope reduced to capture-only.**
> The conversational surface originally shipped here (`ask_hermes`, `escalate_to_gemini`,
> `HERMES_TOOLS`, `HERMES_SYSTEM_PROMPT`) was benchmarked against the live model at commit
> `a7e8e58` and failed decisively: only 1 of 6 requests that needed Gemini actually called
> `escalate_to_gemini` — the rest invented plausible-but-wrong tool calls ("what's the weather
> in Hyderabad tomorrow" called `play_on_youtube` and actually opened YouTube for 183 seconds,
> then reported "I've played the weather forecast for Hyderabad"). A much tighter prompt
> (explicit capability list, negative instructions, few-shot examples, temperature 0) still
> scored 0/6 on escalation. This is not a prompt-tuning gap. The project owner decided Hermes
> is capture-only going forward: all conversation goes to Gemini via the existing
> `llm/gemini.py::ask_gemini`, and Hermes exists solely to power automatic memory capture
> (`extract_capture`/`parse_capture`) and local embeddings. The steps below reflect what was
> actually shipped, not the original 8-tool-tier design.

> **Post-implementation note (2026-08-22): relative-date benchmark and the past-date guard.**
> `due_date` extraction was benchmarked against the live model with today fixed at Saturday
> 2026-08-22. The original prompt (just `Today is {today}.`) scored 2/5 on relative-date
> phrases: "finish the auth refactor by next Tuesday" resolved to 2026-08-30 (a **Sunday**;
> correct is 2026-08-25), "the grant deadline is this Friday" resolved to 2026-08-26 (a
> **Wednesday**; correct is 2026-08-28), and "ship the release next Monday" resolved to
> 2026-08-28 (a **Friday**; correct is 2026-08-24). Adding the weekday name of today plus a
> no-past-dates instruction to the prompt (see the `due_date` bullet below) improved this to
> 3/5 — but one case still returned 2026-08-21, a date **in the past**, despite the explicit
> instruction. Prompting alone is not sufficient to prevent a past date from reaching
> `store.add_task(due_date=...)`, which drives the overdue-commitment reminders — a wrong-past
> date there fires a reminder the instant it is written. `parse_capture` now takes this
> deterministically out of the model's hands: any `due_date` that parses as ISO but falls
> before `today` (an optional parameter, defaulting to the real date, so this is unit-testable
> without depending on the system clock) is dropped to `None` rather than trusted. A `None`
> due date is strictly better than a wrong past one — the residual inaccuracy on phrases like
> "next Monday" landing on the wrong *future* day is accepted and out of scope; this guard
> only closes the past-date failure mode, it is not a date parser.

**Files:**
- Create: `llm/hermes.py`
- Create: `tests/test_hermes.py`

**Interfaces:**
- Consumes: `config.settings.HERMES_MODEL`, `OLLAMA_HOST`, `OLLAMA_NUM_GPU` (Task 1).
- Produces:
  - `hermes.parse_capture(raw: str, today: date = None) -> dict | None` — pure, normalizes and validates one JSON payload; `today` defaults to the real date and exists so the past-due-date guard is unit-testable without depending on the system clock
  - `hermes.extract_capture(user_text: str, reply: str) -> dict | None` — never raises; degrades to `None` if the underlying LLM call fails
  - `hermes.is_available() -> bool`
  - `hermes.CAPTURE_KINDS: set[str]`
  - `hermes.ENTITY_TYPES: set[str]`
  - `hermes.CAPTURE_PROMPT: str`

- [ ] **Step 1: Write the failing parser tests**

`parse_capture` is the one piece of Hermes handling worth heavy testing — it is pure, and it is where a small model's sloppiness actually lands. Create `tests/test_hermes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hermes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.hermes'`.

- [ ] **Step 3: Implement llm/hermes.py**

Create `llm/hermes.py`:

```python
# llm/hermes.py
"""Local Hermes 3 brain, served by Ollama -- capture-only.

This module used to also handle live conversation: Hermes 3 8B bound to 8
tools, self-escalating to Gemini via an escalate_to_gemini tool when a
request exceeded its tier. That was benchmarked against the live model and
failed decisively -- only 1 of 6 requests that needed Gemini actually
escalated; the rest invented plausible-but-wrong tool calls (e.g. "what's
the weather in Hyderabad tomorrow" called play_on_youtube and opened
YouTube for 183 seconds). Prompt tightening did not fix it. The owner's
decision: all conversation goes to Gemini via llm/gemini.py::ask_gemini.
Hermes now exists only to power automatic memory capture (extract_capture /
parse_capture) and local embeddings -- do not restore the conversational
surface without a new benchmark showing it works.
"""
import json
import re
from datetime import date, timedelta

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from config.settings import HERMES_MODEL, OLLAMA_HOST, OLLAMA_NUM_GPU

CAPTURE_KINDS = {"fact", "commitment", "decision", "idea", "preference"}
ENTITY_TYPES = {"project", "person", "topic"}

REQUEST_TIMEOUT = 30
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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
- due_date: ISO YYYY-MM-DD if a deadline was stated, else null. Today is {today}, a
  {today_weekday}. Work out any relative date ("next Tuesday", "this Friday", "tomorrow")
  as an offset from {today} ({today_weekday}), never from any other day. For reference,
  tomorrow is {tomorrow} ({tomorrow_weekday}). A due_date before {today} is never correct --
  if you cannot work out a date on or after {today}, use null instead of guessing.

Conversation:
User: {user_text}
Jarvis: {reply}"""

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=HERMES_MODEL, base_url=OLLAMA_HOST,
                          temperature=0.4, num_gpu=OLLAMA_NUM_GPU,
                          client_kwargs={"timeout": REQUEST_TIMEOUT})
    return _llm


def is_available() -> bool:
    """True if the Ollama server answers. Used to skip Hermes without raising."""
    import requests
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


def parse_capture(raw: str, today: date = None):
    """Normalize one capture payload from Hermes. Returns None if there is nothing to store.

    Small models wrap JSON in prose or fences, emit bare strings where objects were asked
    for, and invent kinds. Every one of those is normalized or rejected here rather than
    downstream.

    `today` defaults to the real system date; pass an explicit `date` in tests so the
    past-due-date check below is deterministic instead of depending on the clock.
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
    if isinstance(due_date, str) and _ISO_DATE.match(due_date):
        # A commitment with no due date is strictly better than one carrying a wrong past
        # date: a past date fires an overdue reminder the instant it's written, while a
        # missing date just waits for a future correction. ISO YYYY-MM-DD strings compare
        # correctly as plain strings (fixed-width, zero-padded), so no date parsing -- and
        # no exception handling -- is needed to make this comparison.
        if due_date < (today or date.today()).isoformat():
            due_date = None
    else:
        due_date = None

    return {"kind": kind, "text": text.strip(), "entities": entities, "due_date": due_date}


def extract_capture(user_text: str, reply: str):
    """Ask Hermes what, if anything, from this exchange is worth keeping.

    Capture runs on a background thread behind the voice loop and must never raise --
    an unreachable or slow Ollama degrades to "nothing to capture" instead.
    """
    llm = _get_llm()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    prompt = CAPTURE_PROMPT.format(
        today=today.isoformat(), today_weekday=today.strftime("%A"),
        tomorrow=tomorrow.isoformat(), tomorrow_weekday=tomorrow.strftime("%A"),
        user_text=user_text, reply=reply)
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
    except Exception as e:
        print(f"[hermes] capture extraction failed: {e}")
        return None

    content = response.content
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return parse_capture(str(content))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hermes.py -v`
Expected: 20 passed. (The original 16 -- 15 `parse_capture` tests plus the `extract_capture`-never-
raises test -- plus 4 added in a post-review fix pass for the past-due-date guard: a past `due_date`
dropped to `None` with the rest of the payload intact, a `due_date` equal to today kept, a future
`due_date` kept, and a prompt-formatting regression test that guards the `{{`/`}}` escaping now that
`CAPTURE_PROMPT` takes two new format keys. A +4 delta that propagates to the cumulative count in
Task 5.)

- [ ] **Step 5: Smoke-test Hermes against the live model**

Ollama must be running. This is a manual check, not a test — model output is not deterministic.

```powershell
uv run python -c "from llm import hermes; print(hermes.is_available()); print(hermes.extract_capture('remind me to finish the auth refactor by Tuesday', 'Got it, noted.'))"
```

Expected: `True`, then a dict with `kind: "commitment"` and a `due_date`.

- [ ] **Step 6: Commit**

```bash
git add llm/hermes.py tests/test_hermes.py
git commit -m "refactor: reduce Hermes to capture-only after failed escalation benchmark"
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

    # Dedup preserving order (first occurrence wins). A payload can name the
    # same entity twice, which would otherwise leave a duplicate id in
    # entity_ids and produce a meaningless self-referential relationship
    # below (add_relationship(id, id, ...)).
    seen_ids = set()
    entity_ids = [eid for eid in entity_ids if not (eid in seen_ids or seen_ids.add(eid))]

    primary_id = entity_ids[0] if entity_ids else None

    # 2. Memory row. entity_id is how a memory attaches to an entity. Guarded
    # like every other step: a DB lock or a malformed entity dict (missing
    # "name"/"type") here must not skip the co-occurrence edges, the
    # commitment task, the daily-note append, the entity pages, or the
    # listener callback below.
    try:
        memory_id = store.add_memory(
            kind=payload["kind"],
            content=payload["text"],
            title=entities[0]["name"] if entities else None,
            entity_id=primary_id,
            tags=[e["name"] for e in entities],
            source="auto_capture",
        )
    except Exception as e:
        print(f"[capture] memory row failed: {e}")
        memory_id = None

    if memory_id is not None:
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
Expected: 16 passed. (Original 14 plus 2 added in a post-review fix pass: a reviewer found
`store.add_memory` was the one write step in `persist_capture` left unguarded — a DB lock or a
malformed entity dict there would propagate out and skip every step after it, including the
co-occurrence edges, the commitment task, the daily-note append, the entity pages, and the
listener callback. It is now wrapped in its own try/except, falling back to `memory_id = None`
so every later step still runs, and the embedding step explicitly skips rather than calling
`vector_store.index_memory(None, ...)`. The reviewer also found that a payload naming the same
entity twice left a duplicate id in `entity_ids`, producing a meaningless self-referential
`add_relationship(id, id, "mentioned_with")` row; `entity_ids` is now deduplicated in place
(order-preserving, first occurrence wins) right after entity creation, before `primary_id` is
read off it. A +2 delta that propagates to the cumulative count below and into Tasks 6-8.)

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -v`
Expected: 63 passed. (Task 2's own count grew from 8 to 14 after the review-driven fixes to `memory/vault.py`, a +6 delta; Task 3's own count grew from 5 to 9 after a review-driven fix pass to `scripts/reindex_embeddings.py`, a further +4 delta; Task 4's own count grew from 16 to 20 after adding the past-due-date guard and its tests, a further +4 delta; Task 5's own count grew from 14 to 16 after the unguarded-memory-row and self-referential-relationship fixes above, a further +2 delta; every cumulative count below carries all four.)

- [ ] **Step 6: Commit**

```bash
git add memory/capture.py tests/test_capture.py
git commit -m "feat: add background capture pipeline writing to SQLite and vault"
```

---

### Task 6: Router

> **Post-implementation note (2026-08-22): scope reduced to capture-only, no escalation.**
> This task was originally specified as a Hermes-first router: call Hermes with an 8-tool
> tier, and if it calls an `escalate_to_gemini` tool, fall back to Gemini with the original
> text. That design is what Task 4's benchmark (see that task's post-implementation note)
> invalidated — only 1 of 6 requests that needed Gemini actually escalated, and the failures
> invented plausible-but-wrong tool calls with real side effects (a weather question called
> `play_on_youtube` and genuinely opened YouTube for 183 seconds). A sharpened prompt at
> temperature 0 still scored 0/6 on escalation. This is not a prompt-tuning gap. The project
> owner's decision, already reflected in `llm/hermes.py` since Task 4, is that Hermes is
> capture-only — it never sees a live user turn. `llm/hermes.py` no longer contains
> `ask_hermes`, `HERMES_TOOLS`, or `escalate_to_gemini`.
>
> With no local brain in the loop, the router has nothing left to route between — it is now a
> thin, single seam around `ask_gemini` that exists purely so `main.py` has one place to call
> and one place where cloud-failure handling (quota exhaustion, any other exception) lives,
> instead of that logic being duplicated or scattered through the GUI/voice loop. The
> `(reply, brain)` tuple and the `"LOCAL"`/`"CLOUD"` indicator are gone with it — there is only
> one brain for conversation now, so a two-way indicator is dead weight. The steps below reflect
> what was actually shipped, not the original Hermes-first design.

**Files:**
- Create: `llm/router.py`
- Create: `tests/test_router.py`

**Interfaces:**
- Consumes: existing `llm.gemini.ask_gemini`.
- Produces: `router.handle(text: str) -> str`. Always returns a string safe to speak aloud;
  never raises.

- [ ] **Step 1: Write the failing tests**

`ask_gemini` is mocked; this task tests error classification and the never-raises contract,
not model quality.

One import-time caveat: `llm/router.py` does `from llm.gemini import ask_gemini`, and
`llm/gemini.py` constructs a `ChatGoogleGenerativeAI` client and binds 26 tools at module
import. So importing the router requires `GOOGLE_API_KEY` to be present in `.env` — it must
be, or the app does not run at all. No network call happens at import, only client
construction, so the tests stay offline.

Create `tests/test_router.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.router'`.

- [ ] **Step 3: Implement llm/router.py**

Create `llm/router.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_router.py -v`
Expected: 6 passed. (The original Hermes-first design had 5 tests covering routing decisions
between two brains; with only one brain left, those became 6 tests covering error
classification instead — pass-through, `429`, `RESOURCE_EXHAUSTED`, case-insensitivity of that
detection, any other exception, and the never-raises contract. A +1 delta that propagates to
the cumulative counts in Tasks 7 and 8.)

- [ ] **Step 5: Commit**

```bash
git add llm/router.py tests/test_router.py
git commit -m "feat: add router as single entry point, capture-only Hermes stays out of conversation"
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


def test_ambiguous_wake_word_mid_sentence_does_not_detect_or_strip():
    text = "the garbage disposal is broken"
    assert wakeword.detect_wake_word(text) is False
    assert wakeword.strip_wake_word(text) == text


def test_ambiguous_wake_word_at_start_detects_and_strips():
    assert wakeword.detect_wake_word("Garbage, what's the weather?") is True
    assert wakeword.strip_wake_word("Garbage, what's the weather?") == "what's the weather?"


def test_leading_wake_word_strips_but_ambiguous_word_survives_later_in_text():
    text = "Jarvis, take out the garbage"
    assert wakeword.detect_wake_word(text) is True
    stripped = wakeword.strip_wake_word(text)
    assert stripped == "take out the garbage"
    assert "garbage" in stripped


def test_wake_word_genuinely_mid_sentence_strips_without_double_space():
    text = "please help jarvis with something"
    assert wakeword.detect_wake_word(text) is True
    assert wakeword.strip_wake_word(text) == "please help with something"


def test_no_wake_word_at_all_is_unchanged():
    text = "let's grab lunch later"
    assert wakeword.detect_wake_word(text) is False
    assert wakeword.strip_wake_word(text) == text


def test_none_and_empty_are_handled_without_raising():
    assert wakeword.strip_wake_word("") == ""
    assert wakeword.strip_wake_word(None) == ""
    assert wakeword.detect_wake_word(None) is False


def test_detect_and_strip_agree_when_detection_is_false():
    text = "the garbage disposal is broken"
    assert wakeword.detect_wake_word(text) is False
    assert wakeword.strip_wake_word(text) == text
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wakeword.py -v`
Expected: 15 passed. (Original 8 plus 7 added in a post-review fix pass: "garbage" is an ordinary
English word, so matching it anywhere in an utterance caused false wakes on unrelated speech and
silent transcript corruption; the fix restricts it to the start of the utterance -- the only place
a wake word actually occurs -- while `jarvis`/`jaress`/`travis` still match anywhere, and both
functions now share one regex so they can never disagree.)

- [ ] **Step 5: Commit**

```bash
git add voice/wakeword.py tests/test_wakeword.py
git commit -m "feat: make wakeword module the single source of wake-word matching"
```

---

### Task 8: Wire the GUI and voice loop

> **Post-implementation correction (as actually built):** the plan below was written
> against an earlier router design that returned `(reply, brain)` and drove a
> LOCAL/CLOUD indicator in the GUI. That design was benchmarked against the live
> model and failed (1 of 6 requests needing Gemini actually escalated; the
> failures invented plausible-but-wrong tool calls with real side effects — a
> weather question opened YouTube). The project owner ruled **Hermes stays
> capture-only**, out of the live conversation path entirely. The router's real,
> shipped interface is `handle(text: str) -> str` — a single string, no tuple, no
> brain indicator anywhere in the GUI. Steps below reflect what was actually
> built, not the original brain-indicator design.

**Files:**
- Modify: `main.py:115-121` (imports), `main.py:201-206` (vault panel), `main.py:282-297` (new `refresh_vault_panel`/`on_capture` methods), `main.py:299-329` (event loop)

**Interfaces:**
- Consumes: `router.handle` (Task 6, real signature `handle(text: str) -> str`); `capture.enqueue(user_text, reply)`, `capture.set_listener(fn)` (Task 5); `wakeword.detect_wake_word`, `wakeword.strip_wake_word` (Task 7); existing `store.list_memories(kind=None, limit=20)`.
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

Note `ask_gemini` is no longer imported here — the router owns that call now, and `main.py` does not need its own try/except around `route_request`: `handle()` never raises, it already converts rate-limit and generic failures into speakable strings internally. `jarvis_tools` is still needed by `build_right_panel`.

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
            reply = route_request(request)

            self.log_to_console("JARVIS", reply)
            self.update_status("PRIMARY DIRECTIVE . ACTIVE", "TRANSMITTING", ACCENT_COLOR)
            speak(reply)

            capture.enqueue(request, reply)
            follow_up_until = time.monotonic() + FOLLOW_UP_WINDOW
```

No try/except wraps `route_request` here: `router.handle` is documented to never raise (it
already catches Gemini's rate-limit and generic failures and returns a speakable string), so
wrapping it again in `main.py` would just be dead defensive code. There is also no `brain`
variable and no LOCAL/CLOUD text anywhere in `update_status` — the status line's suffix is a
static `"ACTIVE"`, not a routing indicator.

- [ ] **Step 6: Verify the full suite still passes**

Run: `uv run python -m pytest` (not bare `uv run pytest` — the project's pytest config is wired
through `python -m pytest`).
Expected: 87 passed. (Note: the cumulative "Expected: N passed" figures earlier in this document,
for Tasks 1-7, were reconciled against a 84-test suite as of Task 7's post-review fix pass. Task 8
added no new tests, but the actual suite observed at this task's completion is 87 — 3 higher than
84. That gap was not tracked down as part of this task; earlier cumulative figures in this
document may still be low and should not be trusted without re-running the suite.)

- [ ] **Step 7: Manual end-to-end verification**

Start Ollama and Obsidian (with the Local REST API plugin enabled), then:

```powershell
uv run main.py
```

Walk the spec's acceptance criteria in order and confirm each. Note: there is no LOCAL/CLOUD
brain indicator to check anywhere below — every reply comes from Gemini via the router, and
Hermes only runs in the background to extract capture payloads after the reply is spoken.

1. Say **"Jarvis, what do you remember about me?"** → the console shows a `JARVIS>` reply and the
   status line reads `PRIMARY DIRECTIVE . ACTIVE / TRANSMITTING` while speaking.
2. Stop Ollama (`Get-Process ollama | Stop-Process`), say **"Jarvis, what's on my calendar
   tomorrow?"** → it still answers normally (Gemini is unaffected by Ollama being down; only
   background capture extraction will fail silently — check the console/logs for
   `[capture] worker error` but confirm the voice loop itself is undisturbed). Restart Ollama
   afterwards.
3. Say **"Jarvis, I'll finish the auth refactor by Tuesday."** Within ~15s of the reply, confirm
   all of:
   - a `MEMORY> [commitment] ...` line appears in the console (from `on_capture`'s
     `self.after(0, lambda: self.log_to_console("MEMORY", ...))`) and the DOCUMENTS panel updates
     (from `on_capture`'s `self.after(0, self.refresh_vault_panel)`)
   - `Journal/<today>.md` in the vault has a new `- HH:MM [commitment] ... [[Auth Refactor]]` line
   - `Entities/Auth Refactor.md` exists
   - `uv run python -c "from memory import store; print(store.list_overdue_tasks(as_of='<a few days later>'))"` lists the task
4. Say **"Jarvis, Ravi is reviewing the auth refactor."** then check the co-occurrence edge exists:
   `uv run python -c "from memory import store; print(store._get_conn().execute('SELECT * FROM relationships').fetchall()[:])"`
   Expected: at least one `mentioned_with` row.
5. Immediately after a reply, say **"and what about Wednesday?"** with no wake word, within
   `FOLLOW_UP_WINDOW` (15s) → it is accepted and answered.
6. Confirm `ENABLE_AUTO_CAPTURE=false` in `.env` cleanly disables capture: `capture.enqueue`
   returns immediately without queuing anything and no `MEMORY>` lines or vault-panel updates
   appear, with no error in the console.

- [ ] **Step 8: Commit**

```bash
git add main.py
git commit -m "feat: route through Hermes-adjacent router, add follow-up window and live vault panel"
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
