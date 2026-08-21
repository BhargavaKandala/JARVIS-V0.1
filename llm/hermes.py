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
from datetime import date

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
- due_date: ISO YYYY-MM-DD if a deadline was stated, else null. Today is {today}.

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


def extract_capture(user_text: str, reply: str):
    """Ask Hermes what, if anything, from this exchange is worth keeping.

    Capture runs on a background thread behind the voice loop and must never raise --
    an unreachable or slow Ollama degrades to "nothing to capture" instead.
    """
    llm = _get_llm()
    prompt = CAPTURE_PROMPT.format(today=date.today().isoformat(),
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
