# GUI text input for typed commands

**Date:** 2026-11-04
**Status:** approved

## Problem

`main.py`'s `VaultCommandCenter` is mic-only. The transcript panel
(`self.console`, a `CTkTextbox`) is output-only, so the sole way to reach
`llm.router.handle()` is to speak the wake word. That makes the app unusable
when the mic is busy or the room is noisy, and it makes manual testing of a
tool or prompt change require talking to the machine.

## Goal

Add a text entry to the GUI that submits a command straight to
`route_request()`, bypassing the wake word, without disturbing the existing
voice loop.

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| TTS on typed replies | Silent, console only | You type when you want a quiet, fast path. Voice turns still speak. |
| Microphone | Stays on | Text is an additional way in, not a replacement mode. |
| Wake word on typed input | Not required | Typing is already an explicit address. |
| `FORCE_TEXT_MODE` | Left unwired | Out of scope; still unreferenced in `config/settings.py`. |

## Concurrency

The shared mutable state is `llm.gemini.conversation_history`, a module-level
list. It belongs to the router/gemini layer, not the GUI, so the lock goes
there:

`llm/router.py` gains a module-level `_turn_lock = threading.Lock()`, and
`handle()` wraps its whole body — including the existing
`conversation_history` reset on exception — in `with _turn_lock:`. Every
caller is then serialized for free: the voice loop, the new text path, and
the scheduler that `automations/scheduler.py` is stubbed for. `main.py` needs
no lock of its own.

The lock is non-reentrant, which is safe: nothing calls `handle()` from
inside `handle()`. `handle()` still never raises, and the lock releases on
the exception path, so a failed turn cannot deadlock every later turn.

Rejected alternatives:

- **Queue drained by `event_loop`.** One worker, no locking, but `listen()`
  blocks on a multi-second `speech_recognition` phrase timeout, so a typed
  command sits unprocessed until it returns. Unpredictable lag.
- **Thread per submission, no lock.** Races `conversation_history` between a
  typed and a spoken turn — exactly the corruption `handle()` already carries
  recovery code for.

## GUI

A `CTkEntry` in the right panel, packed `side="bottom"` *before* the console
so the console keeps `fill="both", expand=True` above it.

```
┌─ right panel ─────────────┐
│ COMMAND DECK              │
│  + save_memory  …         │
│                           │
│ AUDIO I/O . TRANSCRIPT    │
│ ┌───────────────────────┐ │
│ │ USER> ...             │ │
│ │ JARVIS> ...           │ │  ← console, expands
│ └───────────────────────┘ │
│ [ type a command...     ] │  ← new CTkEntry
└───────────────────────────┘
```

Placeholder `type a command...`, bound to `<Return>`.

## Flow on Enter

1. Read and strip the entry; return early if empty.
2. Clear the entry, disable it, set its placeholder to `working...`.
3. `log_to_console("USER", text)`.
4. Spawn a daemon thread that calls `route_request(text)`, then
   `log_to_console("JARVIS", reply)` and `capture.enqueue(text, reply)`.
5. Re-enable the entry and restore its placeholder in a `finally`.

No wake-word check. No `speak()`.

## Status label

The text path deliberately does not touch `core_status_label` or
`main_state_label`. `event_loop` rewrites both to `AWAITING AUDIO` on every
iteration, so a typed turn would only flicker them. Feedback lives on the
entry itself (disabled + `working...`) and in the transcript.

## Error handling

`route_request` already swallows everything and returns a speakable string,
so the text path inherits the rate-limit and generic-error replies. The
thread body still gets a `try/except` logging `SYS_ERROR`, matching
`event_loop`'s guard, so a failure in `log_to_console` or `capture.enqueue`
cannot kill the thread silently. Re-enabling the entry goes in a `finally` so
a raise cannot leave the input permanently disabled.

All widget mutation from the worker thread goes through the existing
`self.after(0, ...)` marshalling idiom — Tkinter widgets may only be touched
from the main thread.

## Testing

Extend `tests/test_router.py` in its existing monkeypatch-`ask_gemini` style:

- Concurrent `handle()` calls serialize — a fake `ask_gemini` that records
  overlap must never observe two turns inside it at once.
- The lock is released after an exception, so a failed turn does not deadlock
  later turns.

The GUI stays untested, consistent with the suite — there is no `test_main.py`
today and Tkinter is not practical to drive headlessly here.

## Out of scope

No `FORCE_TEXT_MODE` wiring, no mic mute button, no command history /
up-arrow recall, no per-turn TTS toggle.
