# JARVIS-OS — Project Guide

*Fable 5 V.A.U.L.T. Architecture — a local-first, voice-driven desktop assistant for Windows.*

Last updated: 2026-08-22, at the end of the `feat/hermes-local-agent` branch.

---

## 1. What this project is

JARVIS-OS is a single-process desktop assistant. It listens for a wake word, transcribes
your speech **on your machine**, answers through Gemini 2.5 Flash with a large tool set,
speaks the reply **on your machine**, and then — this is the new part — quietly decides
whether anything you just said is worth remembering and files it into your Obsidian vault
without you ever saying "remember this."

There is no server and no client. `main.py` runs one desktop process: a CustomTkinter GUI
on the main thread, a voice loop on a background thread, and a memory-capture worker on a
third daemon thread.

**What leaves your machine:** only the Gemini conversation call, and the vision tool if you
explicitly ask about your screen. Speech-to-text, text-to-speech, memory extraction, and
embeddings are all local.

---

## 2. The four moving parts

| Layer | What it does | Where it runs |
|---|---|---|
| **Ears** — faster-whisper `small.en` | Transcribes your speech, CPU int8 | Local |
| **Brain** — Gemini 2.5 Flash | Answers the question, calls up to 26 tools, multi-hop | Cloud |
| **Voice** — Kokoro v1.0 ONNX | Speaks the reply | Local |
| **Memory** — Hermes 3 8B via Ollama | Decides what to remember and files it | Local |

### The turn, end to end

```
listen()  ──►  wake word?  ──►  strip wake word  ──►  router.handle(text)
                                                            │
                                                            ▼
                                                     ask_gemini  (cloud)
                                                            │
                                                            ▼
                                                        speak(reply)
                                                            │
                                            capture.enqueue(request, reply)
                                                            │  (returns instantly)
   ┌────────────────────────────────────────────────────────┘
   ▼   background daemon thread
extract_capture  ──►  parse_capture  ──►  persist_capture
  (Hermes, local)      (pure, strict)         │
                                              ├─► SQLite: memory row + embedding
                                              ├─► SQLite: entities + relationships
                                              ├─► SQLite: task row (if a deadline)
                                              ├─► Obsidian: daily-note line
                                              └─► Obsidian: entity pages
                                                            │
                                                            ▼
                                               GUI vault panel refreshes
```

Capture never blocks the voice loop. `enqueue` puts the turn on a queue and returns.

---

## 3. Features

### Voice loop

- **Wake word with homophone tolerance.** Whisper reliably mishears "Jarvis," so
  `voice/wakeword.py` also accepts `jaress`, `travis`, and `garbage`.
- **Follow-up window.** For **15 seconds** after a reply you can keep talking without
  repeating the wake word (`FOLLOW_UP_WINDOW` in `main.py`).
- **Hallucination filtering.** Whisper transcribes silence as "Thanks for watching!" and
  similar; those are dropped before they reach the brain.

### Memory — the second brain

Your vault gets two kinds of file, both written automatically:

**Daily notes** at `Journal/YYYY-MM-DD.md`, appended one line per capture:

```markdown
- 14:32 [commitment] The user committed to finishing the auth refactor. [[Auth Refactor]]
- 15:07 [decision] The user decided to use SQLite for JARVIS. [[SQLite]] [[JARVIS]]
```

**Entity pages** at `Entities/<Name>.md`, created once per person, project, or topic, so
Obsidian's graph view and Backlinks pane actually connect things.

Every capture is classified as one of five kinds — `fact`, `commitment`, `decision`,
`idea`, `preference` — and small talk is correctly ignored. Real examples from this machine:

```
"I've decided to use SQLite instead of Postgres for JARVIS."
   -> decision, entities: SQLite, Postgres, JARVIS

"My sister Priya is a doctor in Chennai."
   -> fact, entities: Priya (person)

"What time is it?"          -> ignored
"Thanks, that's all."       -> ignored
```

### Under the hood

- **Dual write.** Everything goes to both Obsidian (human-readable) *and* SQLite
  (`data/jarvis.db`, queryable). Each write is independently guarded — if Obsidian is
  closed, SQLite still gets it, and vice versa.
- **Semantic search** over your memories using local `nomic-embed-text` embeddings and
  brute-force cosine similarity in numpy. No vector database.
- **Knowledge graph.** `entities` + `relationships` tables in SQLite. Two entities named in
  the same capture get a `mentioned_with` edge. This is what makes the graph view useful —
  before this branch, those tables existed but nothing ever filled them.
- **Commitment tracking.** A capture with a deadline also creates a task row, which
  `list_overdue_tasks()` and the daily briefing surface later.

### Gemini's tool set (26 tools)

Memory (9) · system: web, YouTube, weather, news, shutdown (5) · project management (8) ·
calendar + GitHub (2) · screen OCR and vision (2).

---

## 4. What was fixed on this branch

26 commits, 8 planned tasks, plus fixes. The test suite went from **0 tests to 101**.

### The big one: Hermes was demoted

Hermes 3 8B was originally built as a *conversational* brain — bound to 8 tools, deciding
for itself when to hand hard requests to Gemini via an `escalate_to_gemini` tool.

**Benchmarked against the live model, it failed.** Only **1 of 6** requests that needed
Gemini actually escalated. The failures weren't quiet:

| Request | What Hermes did |
|---|---|
| "What's the weather in Hyderabad tomorrow?" | Called `play_on_youtube` — **actually opened YouTube**, 183s — then said "I've played the weather forecast" |
| "What's on my calendar this week?" | Called `get_recent_memories` |
| "Analyze my whole codebase" | Called `search_memory` |
| "Add the auth refactor to my tasks for Tuesday" | Called `remember_fact` — no due date, wrong store |

A much tighter prompt with an explicit capability list, negative instructions, few-shot
examples, and temperature 0 still scored **0/6**. Not a prompt-tuning gap.

The same model is *excellent* at extracting memories. So Hermes was reduced to capture-only
and all conversation goes to Gemini. Removing the conversational surface also dropped the
`pywhatkit` import chain, cutting the test suite from **194 seconds to 2**.

### Data-safety bugs found and fixed

- **Entity pages could be destroyed.** `ensure_entity_page` treated "page absent" and "I
  couldn't read the page" identically, then PUT — which *replaces*. One timed-out read
  against a page you'd been writing notes in would silently overwrite it with a stub. It ran
  for every entity of every capture. Now it only writes when absence is *confirmed*.
- **`save_memory` could erase a whole day of captures.** Filenames went to the vault
  unsanitized, so a filename containing `Journal/2026-08-22` would PUT-replace that day's
  accumulated notes. Now sanitized.
- **The embeddings migration could wipe all your vectors.** It purged old-model rows
  unconditionally — so if Ollama died mid-run, you'd lose every embedding with zero
  replacements written. Now scoped to rows actually re-embedded, and backups are timestamped
  so a same-day re-run can't overwrite the real snapshot.
- **A failed memory write aborted everything after it.** `add_memory` was the one unguarded
  step; if it threw, the entity pages, graph edges, task row, and daily note were all
  skipped. Now independently guarded.

### Correctness and robustness

- **Tkinter thread safety.** The voice loop touched GUI widgets directly from a background
  thread — a real crash risk on Windows. `log_to_console`, `update_status`, and
  `refresh_vault_panel` are now self-marshalling via `self.after(0, ...)`, so every caller is
  safe regardless of thread.
- **The voice loop could die silently.** An unplugged or busy microphone raises `OSError`,
  which killed the loop thread — orb still spinning, status still reading "AWAITING AUDIO,"
  assistant permanently deaf. Now guarded, with errors surfaced to the console panel.
- **One bad turn could wedge the whole session.** Gemini's history trim can slice a
  `ToolMessage` away from its `AIMessage`; Gemini then rejects every subsequent turn until
  restart. The router now resets history when a turn fails.
- **"garbage" was breaking ordinary speech.** As a wake word it matched anywhere, so *"the
  garbage disposal is broken"* both falsely woke JARVIS **and** was rewritten to *"the
  disposal is broken"* before the model saw it. It's now accepted only at the start of an
  utterance; `jarvis`/`jaress`/`travis` still match anywhere.
- **Embeddings moved off the cloud.** Auto-capture on Gemini embeddings would have meant a
  cloud call every single turn. Now local. A permanent `WHERE model = ?` filter makes the
  3072-vs-768 dimension mismatch structurally impossible.
- **Silent vault failures.** Write results were discarded, so a rejecting Obsidian looked
  exactly like success. Now logged.
- **`uv.lock` was never regenerated**, so a fresh `uv sync` produced an environment that
  couldn't start. Fixed, and `pytest` moved out of runtime dependencies.

---

## 5. Customizations made for this machine

Two things were adapted specifically to your setup, both deliberate.

### GPU inference is disabled

Your Ollama build cannot use the RTX 3050:

```
llama-server process has terminated: exit status 0xc0000409
CUDA error: device kernel image is invalid
```

Every Ollama client therefore passes `num_gpu=0`. CPU is genuinely fast here:

| Operation | CPU (`num_gpu=0`) |
|---|---|
| `nomic-embed-text` embedding | 0.36s |
| `hermes3:8b` cold start | 9.2s |
| `hermes3:8b` warm, short reply | 0.87s |

If you ever fix the CUDA build, set `OLLAMA_NUM_GPU` to a non-zero value in `.env` — no code
change needed. (Your pre-existing `llama3-cpu` and `qwen3-cpu` models suggest you'd hit this
before.)

### Hermes is capture-only

Covered in §4. The reasoning is recorded in `llm/hermes.py`'s and `llm/router.py`'s module
docstrings, including the benchmark numbers, so nobody restores it without new evidence.

---

## 6. Setup

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ and `uv` | Package manager |
| **Ollama** with `hermes3:8b` and `nomic-embed-text` | `ollama pull hermes3:8b && ollama pull nomic-embed-text` (~5 GB) |
| `kokoro-v1.0.onnx` + `voices-v1.0.bin` in repo root | TTS models, not committed |
| Obsidian + "Local REST API" plugin | Optional — degrades gracefully |
| Tesseract-OCR on `PATH` | Optional — only for `read_screen_text` |
| Google Cloud OAuth JSON | Optional — only for calendar |

### `.env`

```ini
GOOGLE_API_KEY=...            # required — the app will not start without it

OPENWEATHER_API_KEY=...       # optional
NEWS_API_KEY=...              # optional
GITHUB_TOKEN=...              # optional

OBSIDIAN_URL=https://127.0.0.1:27124
OBSIDIAN_API_KEY=...

OLLAMA_HOST=http://127.0.0.1:11434
HERMES_MODEL=hermes3:8b
EMBED_MODEL=nomic-embed-text
ENABLE_AUTO_CAPTURE=true
OLLAMA_NUM_GPU=0
```

> ⚠️ **Your current `.env` has `OBSIDIAN_URL=https://127.0.0.1:27124/c`.** That trailing
> `/c` makes every vault write target a path the Local REST API doesn't serve, so **no
> vault writes will land**. Remove the `/c`. Check the port too — some plugin versions
> default to `27123`.

### Install

```powershell
uv venv
uv pip install -r requirements.txt
```

---

## 7. Starting sequence

**Order matters.** Start these before launching the app:

1. **Ollama** — must be running. Verify:
   ```powershell
   ollama list          # should show hermes3:8b and nomic-embed-text
   ```
2. **Obsidian** — open, with the Local REST API plugin enabled. *(Skip if you don't want
   vault writes; SQLite still records everything.)*
3. **Launch:**
   ```powershell
   uv run main.py
   ```

What you'll see, in order:

```
Loading local Whisper model (This takes 3-5 seconds on CPU)...
Calibrating microphone to your room's background noise (Please stay quiet for 2 seconds)...
```

**Stay quiet during calibration** — it sets the silence threshold for the whole session. The
GUI then opens and the status reads `AWAITING AUDIO`.

### First run only

If you have memories from before this branch, migrate their embeddings from Gemini's
3072-dim vectors to local 768-dim ones:

```powershell
uv run python scripts/reindex_embeddings.py
```

It backs the database up first and is safe to re-run. *(Already done on this machine —
7 memories migrated, backup at `data/jarvis.db.bak-20260822-031526-980455`.)*

---

## 8. Using it

Say **"Jarvis"** followed by your request. For 15 seconds after each reply you can keep
talking without the wake word.

```
"Jarvis, what's the weather in Hyderabad?"
"Jarvis, what's on my calendar this week?"
"Jarvis, what's on my screen?"              — local OCR, no cloud
"Jarvis, explain what's on my screen"       — sends a screenshot to Gemini
"Jarvis, create a project called Auth Refactor"
"Jarvis, give me my daily briefing"
"Jarvis, shut down"
```

**You don't need to ask it to remember anything.** Just talk:

> "I need to finish the auth refactor by next Tuesday."

That silently becomes a commitment in SQLite, a task row with a due date, a line in today's
daily note, and an `Auth Refactor` entity page — while the conversation carries on.

The left GUI panel shows your most recent captures live, and each new one is announced in
the console panel as `MEMORY> [commitment] ...`.

To turn capture off, set `ENABLE_AUTO_CAPTURE=false` in `.env`.

### Tests

```powershell
uv run pytest          # 101 tests, ~7 seconds
```

---

## 9. Known limitations

**Relative weekday dates are unreliable.** This is the one I could not fully fix. On
Saturday 2026-08-22, "next Tuesday" resolved to `2026-08-29` instead of `2026-08-25`.
Measured accuracy is 2/5 correct; adding weekday context to the prompt got it to 3/5, and no
further.

A deterministic guard drops any due date **before today**, so a commitment never lands
already-overdue — but wrong *future* dates still get through. Fixing this properly needs a
date-parsing dependency (`dateutil` or `dateparser`), which was out of scope. **If you want
accurate deadlines, say the date explicitly: "by August 25th" rather than "next Tuesday."**

Other things worth knowing:

- **Queued captures are lost on shutdown.** The worker is a daemon thread and `shutdown_system`
  calls `os._exit(0)`. On CPU a capture takes tens of seconds, so "Jarvis, shut down" will
  usually drop the last one.
- **There is no "forget" tool.** Nothing in the codebase deletes a memory or task by voice.
  Wrong captures have to be removed from `data/jarvis.db` or the vault by hand.
- **The 15-second follow-up window leaves the mic open**, so room conversation can be picked
  up as a command — and captured as memory.
- **`main.py` has no automated test coverage.** The GUI and voice loop were verified by
  inspection only.
- **`main.py` lines 1–102 are a commented-out earlier GUI**, kept for reference. Not a toggle.

---

## 10. Map of the code

```
main.py                      GUI + voice loop  (live class: VaultCommandCenter)
llm/
  router.py                  handle(text) -> str   ← the one seam main.py calls
  gemini.py                  ask_gemini, 26 tools  ← deliberately untouched
  hermes.py                  extract_capture, parse_capture  (capture only)
memory/
  capture.py                 queue + daemon worker + persist_capture
  vault.py                   Obsidian REST: daily notes, entity pages
  store.py                   SQLite: memories, entities, relationships, tasks
  vector_store.py            local embeddings + cosine search
voice/
  listener.py                faster-whisper
  wakeword.py                WAKE_WORDS, detect_wake_word, strip_wake_word
  speaker.py                 Kokoro TTS
skills/                      the tool implementations
scripts/reindex_embeddings.py    one-shot embedding migration
tests/                       101 tests
```

**If you change one thing, know this:** `llm/gemini.py` is the conversation path and was
kept byte-identical throughout this work. `llm/router.py` is where cloud-failure policy
belongs. `memory/capture.py`'s per-step guards are load-bearing — collapsing them into a
shared helper would conflate unrelated failures and reintroduce the bug where one failed
write aborted all the others.
