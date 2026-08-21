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

from config.settings import HERMES_MODEL, OLLAMA_HOST, OLLAMA_NUM_GPU
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
                          temperature=0.4, num_gpu=OLLAMA_NUM_GPU,
                          client_kwargs={"timeout": REQUEST_TIMEOUT})
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
