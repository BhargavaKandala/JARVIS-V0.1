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
from typing import Optional

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


def get_note(path: str) -> Optional[str]:
    """Return note contents, or None if absent or unreachable."""
    try:
        response = requests.get(_url(path), headers=HEADERS, verify=False, timeout=TIMEOUT)
    except Exception:
        return None
    return response.text if response.status_code == 200 else None


def note_exists(path: str) -> Optional[bool]:
    """True if the note is confirmed present, False if confirmed absent (404),
    or None if that could not be determined (timeout, TLS hiccup, any other
    exception, or a non-200/404 status such as a 5xx). Callers that would
    otherwise PUT-replace an existing note on an ambiguous read must treat
    None as "do nothing" -- see ensure_entity_page."""
    try:
        r = requests.get(_url(path), headers=HEADERS, verify=False, timeout=TIMEOUT)
    except Exception:
        return None
    return True if r.status_code == 200 else (False if r.status_code == 404 else None)


def append_daily_note(line: str, when: date = None) -> bool:
    """Append one line to today's daily note, creating it if needed."""
    path = daily_note_path(when)
    response = requests.post(_url(path), headers=HEADERS, data=f"{line}\n".encode("utf-8"),
                             verify=False, timeout=TIMEOUT)
    return _ok(response)


def ensure_entity_page(name: str, type_: str) -> bool:
    """Create Entities/<Name>.md if it does not already exist. No-op if present
    -- and no-op (never destructive) when presence can't be determined, since
    a PUT here replaces the file wholesale. Only a confirmed 404 may create it."""
    path = entity_note_path(name)
    if note_exists(path) is not False:
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
