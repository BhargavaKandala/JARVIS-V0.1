# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

JARVIS-OS ("Fable 5 V.A.U.L.T. Architecture") — a local-first, voice-driven desktop assistant for Windows, evolving from a reactive voice assistant (v0.2) into an "AI executive assistant" (v0.3): it remembers commitments, tracks projects, and can chain multiple tool calls per turn instead of just parroting one tool's output. It listens for a wake word, transcribes speech locally, routes the request through Gemini 2.5 Flash with a set of LangChain tools, speaks the response locally, and persists memories both as Markdown files in an Obsidian vault (human-readable) and in a local SQLite index (queryable/searchable). There is no server/client split — `main.py` runs a single desktop process with a CustomTkinter GUI and a background worker thread.

Note: Gemini is no longer the *only* cloud call — `skills/vision_tools.py::explain_screen` sends a screenshot to Gemini's vision model when the user explicitly asks about their screen. This is opt-in by construction (only ever triggered by a voice request), but it is a new off-device data flow worth knowing about. `read_screen_text` (local OCR via pytesseract) has no cloud exposure and is the preferred default for screen-reading.

## Commands

Package manager is `uv`; there is no test suite, linter, or build step configured (`tests/` is empty, no pytest/ruff config exists).

```powershell
uv venv                            # create the venv (.venv)
uv pip install -r requirements.txt # install deps (requirements.txt is generated from pyproject.toml)
uv run main.py                     # run the app (starts the GUI + voice loop)
```

Regenerate `requirements.txt` after editing dependencies in `pyproject.toml`:
```powershell
uv pip compile pyproject.toml -o requirements.txt
```

Runtime requirements before `main.py` will work:
- `.env` with `GOOGLE_API_KEY` (Gemini), plus optional `OPENWEATHER_API_KEY`, `NEWS_API_KEY`, `GITHUB_TOKEN`, and `OBSIDIAN_URL`/`OBSIDIAN_API_KEY`.
- Obsidian desktop app running locally with the "Local REST API" community plugin enabled (memory tools call `https://127.0.0.1:27124` by default — note the port, some plugin versions default to `27123`; check your plugin settings if `save_memory`/`read_memory` can't connect). If Obsidian isn't running, memory tools fall back to the local SQLite index instead of failing outright.
- `kokoro-v1.0.onnx` and `voices-v1.0.bin` model files in the repo root (TTS engine; not committed — see `.gitignore`).
- Tesseract-OCR (the Windows binary, not a pip package) installed and on `PATH` for `read_screen_text` to work — get it from the [UB-Mannheim Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki). Without it, `read_screen_text` returns a friendly error string rather than crashing.
- For `get_calendar_events`: a Google Cloud OAuth client JSON saved at `config/google_calendar_credentials.json` (gitignored). First use opens a one-time browser consent screen; the refresh token is cached at `data/google_calendar_token.json` (gitignored). Without this file, the tool degrades to "calendar not connected" rather than erroring.
- `data/jarvis.db` (SQLite) is created automatically on first use of any memory/project tool — no setup needed, but back it up if you care about accumulated memory/project state (it's gitignored).

## Architecture

**Entry point is `main.py`.** The actual orchestration logic lives in `llm/gemini.py`.

Runtime flow, one iteration of the loop in `main.py`'s `event_loop` (runs on a background thread so the Tkinter GUI never blocks):
1. `voice/listener.py::listen()` — blocks on the mic via `speech_recognition`, transcribes with a locally-loaded `faster-whisper` `small.en` model (CPU, int8). Filters out common Whisper hallucinations (silence transcribed as "Thanks for watching!" etc).
2. Wake-word check is a plain substring match against a hardcoded list (`"jarvis"`, `"jaress"`, `"travis"`, `"garbage"` — homophone fuzzing for STT misfires) inline in `main.py`. `voice/wakeword.py` defines a `detect_wake_word()` helper but it is currently unused by `main.py`.
3. `llm/gemini.py::ask_gemini()` — sends the transcript to `gemini-2.5-flash` via `langchain_google_genai`, bound with `jarvis_tools`. Unlike a single-shot call, this now runs a multi-hop agent loop (up to `MAX_TOOL_HOPS = 5`): all tool calls the model requests in a turn are executed (not just the first), their results are fed back as `ToolMessage`s, and the model gets a final synthesis turn to phrase the spoken response in its own words. Conversation history persists across calls in a module-level list (trimmed to `MAX_HISTORY_MESSAGES = 20`), and today's date is injected into the system prompt each turn so the model can resolve relative dates ("tomorrow", "Tuesday") itself before calling date-taking tools.
4. `voice/speaker.py::speak()` — synthesizes with local Kokoro v1.0 (ONNX) and plays back synchronously via `sounddevice`.

There is still no autonomous/scheduled behavior anywhere — `automations/scheduler.py` remains an empty stub. Daily-briefing and overdue-task logic (`skills/project_tools.py::build_daily_briefing`) is pull-based (the user has to ask), but is written as a plain function separate from its `@tool` wrapper specifically so a future scheduler can call it directly without rework.

**Tool/skill registration (`llm/gemini.py`):** `jarvis_tools` is assembled at import time from static imports across six modules — `skills/memory_tools.py`, `skills/system_tools.py`, `skills/project_tools.py`, `skills/calendar_tools.py`, `skills/github_tools.py`, `skills/vision_tools.py` — plus a dynamic skill-discovery loader (every subdirectory of `skills/` containing a `SKILL.md`, case-sensitive, is imported as `skills.<dir>.run` and any `.invoke`-having attribute is appended). The dynamic loader currently has no matching folders — it's dead weight kept for future expansion, not exercised today. Errors during dynamic import are silently swallowed (bare `except: pass`).

**Shutdown**: `skills/system_tools.py::shutdown_system` is the only implementation (returns a string, no actual `shutdown` syscall — commented out). `llm/gemini.py::ask_gemini` special-cases the tool name `"shutdown_system"` to call `os._exit(0)` right after it executes, because `sys.exit()` hangs the Tkinter main loop.

**Memory is dual-write: Obsidian + SQLite.** `skills/memory_tools.py::save_memory` PUTs a Markdown file to the Obsidian Local REST API (human-readable, unchanged behavior) *and* writes a row to `memories` in `data/jarvis.db` via `memory/store.py`, then indexes it for semantic search via `memory/vector_store.py` (Gemini `gemini-embedding-001`, brute-force cosine similarity in `numpy` — no separate vector DB). Each write path is independently try/excepted, so a down Obsidian instance doesn't block the SQLite write or vice versa. `read_memory` falls back to the SQLite index if the Obsidian GET 404s. New tools beyond the original two: `search_memory` (semantic search, not exact filename), `remember_fact`, `remember_preference`/`recall_preference`, `log_decision`, `get_recent_memories`.

**Knowledge graph** is a plain SQLite adjacency model (`entities` + `relationships` tables in `memory/store.py`), not a graph database — deliberately, to avoid a heavyweight dependency at personal-assistant scale. `get_or_create_entity`/`add_relationship`/`get_related_entities` are the primitives; nothing currently populates `relationships` automatically, tools would need to call `add_relationship` explicitly to connect e.g. a project to a GitHub repo entity.

**Project management** (`skills/project_tools.py`) tracks projects/tasks/decisions in the same SQLite DB: `create_project`, `update_project_status`, `add_project_task`, `complete_project_task`, `get_project_status` (enriches with live GitHub issue counts if the project's `github_repo` field is set), `list_projects_summary`. `remember_commitment` is the mechanism behind "you said you'd finish X by Tuesday" follow-ups — it stores a task with a `due_date` and the original utterance as `source_text`; `store.list_overdue_tasks()` is what a future scheduler or the daily briefing surfaces it through.

**Calendar/GitHub** (`skills/calendar_tools.py`, `skills/github_tools.py`) are read-only integrations. Calendar uses Google OAuth (`InstalledAppFlow`, one-time browser consent, cached token); GitHub uses plain `requests` against the REST API (no SDK dependency), optionally authenticated via `GITHUB_TOKEN` for private repos/higher rate limits. Both degrade to empty results/friendly strings rather than raising if not configured.

**Screen understanding** (`skills/vision_tools.py`): `read_screen_text` does local OCR via `pytesseract` over a `PIL.ImageGrab` screenshot — no network call. `explain_screen` sends the same screenshot to a separate `ChatGoogleGenerativeAI` vision-model instance (constructed locally in this file, not imported from `llm/gemini.py`, to avoid a circular import). Both tools are gated to explicit user invocation only via the system prompt (`llm/prompts.py`) — there is no background/continuous screen capture anywhere in the codebase.

**`main.py` currently contains two full GUI implementations**: an earlier version commented out at the top of the file (lines 1–102), and the live `VaultCommandCenter` class below it. When editing the GUI, edit the live class; the commented block is dead code kept for reference, not a toggle.

`config/settings.py` loads `.env` via `python-dotenv`, plus Calendar OAuth paths (`GOOGLE_CALENDAR_CREDENTIALS_PATH`, `GOOGLE_CALENDAR_TOKEN_PATH`) and `GITHUB_TOKEN`. It also has a `FORCE_TEXT_MODE = True` flag that is currently unused/unreferenced elsewhere in the codebase.

`automations/scheduler.py` is an empty stub (no scheduled-task logic implemented yet) — the intended future home for autonomous/proactive triggers (e.g. an unprompted morning briefing), deliberately deferred; see `build_daily_briefing()` above for the pull-based logic it would call.
