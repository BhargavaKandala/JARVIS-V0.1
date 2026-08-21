import os
import importlib
from datetime import date
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from llm.prompts import SYSTEM_PROMPT
from config.settings import GOOGLE_API_KEY

# 1. Import Obsidian Memory
from skills.memory_tools import (
    save_memory, read_memory, search_memory, remember_fact,
    remember_preference, recall_preference, log_decision, get_decisions, get_recent_memories,
)

# 2. BRING BACK YOUR OLD TOOLS!
from skills.system_tools import open_website, play_on_youtube, get_weather, get_news, shutdown_system

# 3. Project management + daily intelligence
from skills.project_tools import (
    create_project, update_project_status, add_project_task, complete_project_task,
    remember_commitment, get_project_status, list_projects_summary, get_daily_briefing,
)

# 4. Calendar + GitHub
from skills.calendar_tools import get_calendar_events
from skills.github_tools import get_github_repo_status

# 5. Screen understanding (opt-in only, see SYSTEM_PROMPT gating)
from skills.vision_tools import read_screen_text, explain_screen

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0.7)

# 6. Add them ALL back to Jarvis's Brain
jarvis_tools = [
    save_memory, read_memory, search_memory, remember_fact,
    remember_preference, recall_preference, log_decision, get_decisions, get_recent_memories,
    open_website, play_on_youtube, get_weather, get_news, shutdown_system,
    create_project, update_project_status, add_project_task, complete_project_task,
    remember_commitment, get_project_status, list_projects_summary, get_daily_briefing,
    get_calendar_events, get_github_repo_status,
    read_screen_text, explain_screen,
]

# Map the tools so the executor knows what function to run
tool_map = {t.name: t for t in jarvis_tools}

# --- FABLE 5 OS: DYNAMIC SKILL LOADER (For future expansion) ---
skills_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
if os.path.exists(skills_dir):
    for branch in os.listdir(skills_dir):
        branch_path = os.path.join(skills_dir, branch)
        if os.path.isdir(branch_path) and "SKILL.md" in os.listdir(branch_path):
            try:
                module = importlib.import_module(f"skills.{branch}.run")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if hasattr(attr, "invoke"):
                        jarvis_tools.append(attr)
                        tool_map[attr.name] = attr
            except Exception as e:
                pass

llm_with_tools = llm.bind_tools(jarvis_tools)

MAX_TOOL_HOPS = 5
MAX_HISTORY_MESSAGES = 20

conversation_history = []

def ask_gemini(user_input: str) -> str:
    global conversation_history

    conversation_history.append(HumanMessage(content=user_input))
    dated_prompt = SYSTEM_PROMPT + f"\nToday's date is {date.today().isoformat()}."
    messages = [SystemMessage(content=dated_prompt)] + conversation_history

    final_response = None
    for _ in range(MAX_TOOL_HOPS):
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        final_response = response

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_fn = tool_map.get(name)

            if tool_fn is None:
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = tool_fn.invoke(args) if hasattr(tool_fn, "invoke") else tool_fn(**args)
                except Exception as e:
                    result = f"Tool '{name}' failed: {e}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

            # GUI SAFE SHUTDOWN OVERRIDE
            # Standard sys.exit() hangs Tkinter. os._exit(0) instantly kills all threads and closes the window.
            if name == "shutdown_system":
                print("[*] Terminating V.A.U.L.T. OS...")
                os._exit(0)

    conversation_history = messages[1:]
    if len(conversation_history) > MAX_HISTORY_MESSAGES:
        conversation_history = conversation_history[-MAX_HISTORY_MESSAGES:]

    if isinstance(final_response.content, list):
        return " ".join(
            b.get("text", "") for b in final_response.content if isinstance(b, dict) and "text" in b
        ).strip()
    if not final_response.content:
        return "I attempted a few steps but couldn't finish — want me to try a different way?"
    return str(final_response.content)
