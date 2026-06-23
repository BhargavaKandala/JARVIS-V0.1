import os
import importlib
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from llm.prompts import SYSTEM_PROMPT
from config.settings import GOOGLE_API_KEY

# 1. Import Obsidian Memory
from skills.memory_tools import save_memory, read_memory

# 2. BRING BACK YOUR OLD TOOLS!
from skills.system_tools import open_website, play_on_youtube, get_weather, get_news, shutdown_system

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0.7)

# 3. Add them ALL back to Jarvis's Brain
jarvis_tools = [
    save_memory, read_memory,
    open_website, play_on_youtube, get_weather, get_news, shutdown_system
]

# Map the tools so the executor knows what function to run
tool_map = {
    "save_memory": save_memory,
    "read_memory": read_memory,
    "open_website": open_website,
    "play_on_youtube": play_on_youtube,
    "get_weather": get_weather,
    "get_news": get_news,
    "shutdown_system": shutdown_system
}

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

def ask_gemini(user_input: str) -> str:
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_input)]
    response = llm_with_tools.invoke(messages)
    
    # 4. Handle the Execution
    if response.tool_calls:
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            
            if name in tool_map:
                # Check if it's a LangChain @tool with an invoke method, otherwise call directly
                if hasattr(tool_map[name], "invoke"):
                    result = tool_map[name].invoke(args)
                else:
                    result = tool_map[name](**args)
                    
                # GUI SAFE SHUTDOWN OVERRIDE
                # Standard sys.exit() hangs Tkinter. os._exit(0) instantly kills all threads and closes the window.
                if name == "shutdown_system":
                    print("[*] Terminating V.A.U.L.T. OS...")
                    os._exit(0)
                    
                return str(result)
                
    if isinstance(response.content, list):
        return " ".join([b.get("text", "") for b in response.content if isinstance(b, dict) and "text" in b]).strip()
    return str(response.content)