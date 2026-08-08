# Hermes Local Agent + Obsidian Second Brain — Design

Date: 2026-08-08
Status: Approved, ready for implementation planning

## Goal

Add Nous Research's Hermes 3 8B as a locally-run reasoning brain (via Ollama) alongside
the existing Gemini 2.5 Flash, and turn the Obsidian vault from a flat dumping ground into
a linked second brain that fills itself without the user having to say "remember this".

Two user-facing outcomes:

1. Common requests are answered locally with no network call.
2. Anything worth keeping from a conversation lands in the vault automatically, filed into
   a dated daily note and cross-linked to entity pages.

## Constraints

Measured on the target machine (the only machine this runs on):

- NVIDIA RTX 3050 Laptop, **4096 MiB VRAM**
- 15.3 GB system RAM, AMD Ryzen 7 6800H
- Ollama already installed (`qwen3:4b`, `llama3:latest` present)

Consequences that shape the design:

- Hermes 3 8B at Q4 (~4.9 GB) does **not** fit entirely in 4 GB VRAM. It partially offloads
  to CPU, giving roughly 5–8 tok/s while Whisper `small.en` and Kokoro are also resident.
  Expect ~8–12s for a local turn. This is a deliberate latency-for-privacy trade.
- Hermes 4 14B is not viable on this hardware for a voice loop.
- `llm/gemini.py` currently binds **26 tools**. Small local models degrade sharply at that
  tool count. Reducing the per-turn tool surface is the single largest reliability lever,
  more important than model size.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Which Hermes | Nous Hermes 3 8B via Ollama | Best tool-calling quality that this hardware can host at all |
| Hermes vs Gemini | Hybrid, Hermes-first with escalation | Common case stays local and private; hard multi-hop work keeps today's proven path |
| Routing mechanism | `escalate_to_gemini` tool | No fixed classification hop on every turn; escalation is a natural fit for the existing loop |
| Capture trigger | Automatic, after every turn | User never has to say "remember this"; runs post-playback so it costs no latency |
| Vault shape | Daily notes + linked entity pages | Chronological capture plus a navigable graph; populates the unused `entities`/`relationships` tables |
| Embeddings | Local `nomic-embed-text` via Ollama | Auto-capture on every turn would otherwise mean a Gemini embedding call per turn |

Explicitly **not** doing:

- Not rewriting `llm/gemini.py`. `ask_gemini` is preserved verbatim as the escalation target.
- Not adding always-on ambient listening. Wake word still gates conversation.
- Not adding a vector database. Brute-force cosine in numpy stays; it is correct at this scale.
- Not implementing the scheduler. `automations/scheduler.py` remains a stub.

## Architecture

### New modules

| Module | Responsibility | Depends on |
|---|---|---|
| `llm/hermes.py` | Ollama-backed Hermes client; exposes `ask_hermes(text) -> HermesResult` and `extract_capture(user_text, reply) -> dict \| None` | `langchain_ollama`, tier-1 tools |
| `llm/router.py` | Escalation orchestrator; exposes `handle(text) -> (reply, brain_used)` | `llm/hermes.py`, `llm/gemini.py` |
| `memory/capture.py` | Background post-turn extraction worker with a queue and a single consumer thread | `llm/hermes.py`, `memory/store.py`, `memory/vault.py`, `memory/vector_store.py` |
| `memory/vault.py` | Obsidian REST writer: daily-note append, entity page creation, wikilink formatting | `requests` |
| `scripts/reindex_embeddings.py` | One-shot embedding migration | `memory/store.py`, `memory/vector_store.py` |

### Modified modules

| Module | Change |
|---|---|
| `main.py` | Calls `router.handle()` instead of `ask_gemini()`; adds follow-up window; enqueues capture after `speak()`; brain indicator + live vault panel |
| `voice/wakeword.py` | Becomes the single source of truth for wake-word matching (currently dead code holding `"hey jarvis"`) |
| `memory/vector_store.py` | Embedder swapped to Ollama `nomic-embed-text`; `search()` filters by embedding model |
| `skills/memory_tools.py` | Raw Obsidian PUT/GET logic extracted into `memory/vault.py`; tool wrappers unchanged in behavior |
| `config/settings.py` | Adds `OLLAMA_HOST`, `HERMES_MODEL`, `EMBED_MODEL`, `ENABLE_AUTO_CAPTURE` |
| `llm/gemini.py` | No logic change. `ask_gemini` stays as-is. |

### Tool tiers

Hermes is bound to **8** tools. The list lives in one constant in `llm/hermes.py` so it can
be tuned after observing real misroutes.

```
HERMES_TOOLS = [
    search_memory, remember_fact, recall_preference, get_recent_memories,
    open_website, play_on_youtube, shutdown_system, escalate_to_gemini,
]
```

Gemini keeps all 26 tools, unchanged.

`escalate_to_gemini` is a real LangChain tool taking one argument (`reason: str`). When the
router sees it in Hermes's tool calls, it abandons the Hermes turn and delegates the
*original* user text to `ask_gemini`.

### Turn flow

```
listen()
  → wake word matched (or inside follow-up window)
  → router.handle(text)
       ├─ ask_hermes(text) answers or calls a tier-1 tool   → (reply, "LOCAL")
       └─ escalate_to_gemini called
          OR Ollama unreachable
          OR Hermes raises
             → ask_gemini(text)                             → (reply, "CLOUD")
  → speak(reply)
  → capture.enqueue(text, reply)      # background, non-blocking
  → follow-up window opens for 15s
```

The router never runs both brains for a successful local turn. Escalation discards the
Hermes attempt entirely rather than passing partial state to Gemini — this keeps
`ask_gemini`'s own history and multi-hop loop coherent.

### Capture pipeline

`memory/capture.py` owns a `queue.Queue` and one daemon consumer thread started at import.
`enqueue()` is non-blocking and returns immediately.

The consumer calls `hermes.extract_capture()`, which prompts Hermes for strict JSON:

```json
{
  "capture": true,
  "kind": "commitment",
  "text": "Finish the auth refactor by Tuesday",
  "entities": [{"name": "Auth Refactor", "type": "project"}],
  "due_date": "2026-08-11"
}
```

- `kind` is one of `fact | commitment | decision | idea | preference`.
- Each entity has a `name` and a `type` of `project | person | topic`. `store.get_or_create_entity`
  takes `(type_, name)` and treats the pair as the identity key, so the type is required, not
  decorative. A bare string in the list is tolerated and defaults to `type: "topic"` — small
  models drop fields, and a mistyped entity is better than a lost one.
- `due_date` is ISO or `null`. Hermes resolves relative dates itself using an injected
  today's date, matching the existing convention in `SYSTEM_PROMPT`.
- `"capture": false` → dropped silently, nothing written.
- Malformed JSON, missing keys, or an unknown `kind` → dropped and logged. Never retried.

On a valid capture, the writes below run, **each independently try/excepted** so one failure
does not block the others (this mirrors the existing dual-write pattern in `save_memory`).
The first entity in the list is the *primary* entity; ordering is significant.

1. **Entities.** For each entity, `store.get_or_create_entity(type_, name)`, collecting ids.
2. **Memory row.** `store.add_memory(kind=..., content=text, entity_id=<primary id>, tags=[names])`
   then `vector_store.index_memory(memory_id, text)`. Note `add_memory` accepts a single
   `entity_id` — that column is how a memory attaches to an entity. `add_relationship` is
   strictly entity-to-entity and is *not* used for the memory link.
3. **Co-occurrence edges.** When a capture names two or more entities,
   `store.add_relationship(primary_id, other_id, "mentioned_with")` for each remaining
   entity. This is what actually fills the `relationships` table. The insert is
   `INSERT OR IGNORE`, so repeated mentions do not duplicate edges.
4. **Commitments.** If `kind == "commitment"` and `due_date` is set,
   `store.add_task(project_name, title=text, due_date=..., source_text=<original utterance>)`,
   where `project_name` is the primary entity's name, or `"Inbox"` when no entity was
   extracted. `add_task` resolves an unknown project through `upsert_project`, which itself
   creates a matching `project` entity — so no pre-creation is needed. This is what makes
   `store.list_overdue_tasks()` surface the commitment later.
5. **Vault.** `vault.append_daily_note(...)` appends one line to `Journal/YYYY-MM-DD.md`:
   `- 14:32 [commitment] Finish the auth refactor by Tuesday [[Auth Refactor]]`
   Then `vault.ensure_entity_page(name)` for each entity, creating `Entities/<Name>.md` with
   YAML frontmatter only if the file does not already exist.

Steps 1–3 are the first code in the project to populate `entities` and `relationships`.
Obsidian backlinks then come for free: every daily-note mention appears on the entity page.

### Obsidian REST details

The Local REST API distinguishes verbs, and `memory/vault.py` relies on this:

- `POST /vault/{path}` — **appends** to an existing file. Used for daily notes.
- `PUT /vault/{path}` — **replaces** file contents. Used by existing `save_memory` and by
  `ensure_entity_page` on first creation only.
- `GET /vault/{path}` — read; a 404 is how `ensure_entity_page` detects absence.

Paths are URL-encoded, matching the existing handling in `skills/memory_tools.py`.

## Listening loop

Two changes in `main.py` and `voice/wakeword.py`:

**Follow-up window.** After `speak()` returns, a 15-second window opens during which
transcribed speech is accepted without a wake word. Any accepted turn resets the window.
The window expires silently — no audio cue, no state visible beyond the GUI status line.
This makes multi-turn exchanges possible without re-invoking the wake word each time.

**Wake word consolidation.** `voice/wakeword.py` currently contains `WAKE_WORD = "hey jarvis"`
and is imported by nothing, while `main.py` hardcodes `["jarvis", "jaress", "travis", "garbage"]`
inline. The homophone list moves into `voice/wakeword.py` as the single source of truth, and
`main.py` calls `detect_wake_word()`. A new `strip_wake_word(text)` removes the matched token
before the transcript reaches the LLM — today `"jarvis what's the weather"` is sent verbatim.

## GUI

- Status line gains a brain indicator: `CORE . LOCAL` or `CORE . CLOUD` per turn, so
  escalation frequency is visible and the tier list can be tuned from observed behavior.
- The **DOCUMENTS (VAULT)** panel is currently hardcoded to fake filenames
  (`Master Plan.md`, `Project Alpha.md`). It is wired to `store.list_memories(limit=5)` and
  refreshed after each successful capture.
- GUI updates from the capture thread are marshalled through `self.after(0, ...)`, since
  Tkinter widgets must only be touched from the main thread.

## Embeddings migration

`gemini-embedding-001` produces 3072-dim vectors; `nomic-embed-text` produces 768-dim.
Mixed dimensions in the `embeddings` table make `vector_store.search()` raise on the
`np.dot` call. Therefore:

1. `scripts/reindex_embeddings.py` copies `data/jarvis.db` to
   `data/jarvis.db.bak-YYYYMMDD` first, then re-embeds every row in `memories` through
   Ollama and rewrites `embeddings`, reporting a count at the end. Safe to re-run.
2. `vector_store.search()` gains a `WHERE e.model = ?` filter bound to the active
   `EMBED_MODEL`, as a permanent guard. A half-finished or abandoned migration then
   degrades to fewer search results instead of crashing the voice loop.

## Failure behavior

| Failure | Behavior |
|---|---|
| Ollama not running | `router.handle` catches the connection error and delegates to `ask_gemini`. Capture worker no-ops and logs one line to the GUI console. Voice loop unaffected. |
| Hermes returns malformed capture JSON | Capture dropped and logged. No retry. |
| Hermes hangs | 30s timeout on the Ollama client, then escalate. |
| Obsidian down | SQLite write still succeeds; vault write logs and is skipped. Existing behavior preserved. |
| Gemini 429 / rate limited | Existing handling in `main.py` stays. Hermes continues serving tier-1 requests offline. |
| Capture thread raises | Caught at the consumer loop boundary; thread survives and processes the next item. |

## Configuration

New entries in `config/settings.py`, all with working defaults so a fresh clone runs:

```python
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
HERMES_MODEL = os.getenv("HERMES_MODEL", "hermes3:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
ENABLE_AUTO_CAPTURE = os.getenv("ENABLE_AUTO_CAPTURE", "true").lower() == "true"
```

`ENABLE_AUTO_CAPTURE=false` disables the capture worker entirely, restoring
explicit-only memory behavior without a code change.

## Dependencies

One new pip dependency: `langchain-ollama`. Added to `pyproject.toml`, then
`uv pip compile pyproject.toml -o requirements.txt`.

Two model pulls (manual, one time):

```powershell
ollama pull hermes3:8b        # ~4.7 GB
ollama pull nomic-embed-text  # ~274 MB
```

## Testing

`tests/` is currently empty and no pytest config exists. This design adds pytest and covers
the pure logic only:

- **`tests/test_capture.py`** — capture JSON parsing: valid payload, malformed JSON,
  missing keys, unknown `kind`, `capture: false`, `due_date` null vs ISO, entity list given
  as bare strings vs typed objects, and the single-entity case producing no relationship.
- **`tests/test_vault.py`** — daily-note path derivation, markdown line formatting,
  wikilink escaping for names containing `[`, `]`, or `/`, entity filename sanitization.
- **`tests/test_router.py`** — escalation decision with both LLM clients mocked: local
  answer, `escalate_to_gemini` call, Ollama connection error, Hermes exception.

Voice, GUI, and live LLM calls stay manual — mocking Whisper, Kokoro and Tkinter would test
the mocks rather than the system.

## Acceptance criteria

1. With Ollama running, "Jarvis, what's my favorite editor?" is answered without a network
   call and the GUI shows `CORE . LOCAL`.
2. With Ollama stopped, the same request still succeeds via Gemini and shows `CORE . CLOUD`.
3. Saying "Jarvis, I'll finish the auth refactor by Tuesday" produces, within ~15s of the
   reply: a dated bullet in `Journal/2026-08-08.md`, an `Entities/Auth Refactor.md` page, a
   row in `entities`, a `memories` row whose `entity_id` points at it, and a task with
   `due_date` 2026-08-11.
4. Saying something naming two entities ("Ravi is reviewing the auth refactor") additionally
   produces a `mentioned_with` row in `relationships`. A single-entity capture correctly
   produces no relationship row.
5. A follow-up spoken within 15 seconds is accepted without the wake word.
6. `scripts/reindex_embeddings.py` completes and `search_memory` returns results afterwards.
7. `pytest` passes.

## Deferred

- Scheduler / proactive morning briefing (`automations/scheduler.py` stays a stub).
- Local vision to replace `explain_screen`'s Gemini call — remains the one deliberate
  cloud dependency alongside escalation.
- Local STT/TTS changes — Whisper and Kokoro are untouched.
- Vault reorganization of notes written before this change; existing flat files stay where
  they are and remain readable via `read_memory`.
