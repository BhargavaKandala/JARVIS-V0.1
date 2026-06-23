# llm/gemini.py
import os
import importlib
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from llm.prompts import SYSTEM_PROMPT
from config.settings import GOOGLE_API_KEY
from skills.memory_tools import save_memory # Keep memory direct for now

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0.7)

# --- FABLE 5 OS: DYNAMIC SKILL LOADER ---
jarvis_tools = [save_memory]
tool_map = {"save_memory": save_memory}

skills_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
for branch in os.listdir(skills_dir):
    branch_path = os.path.join(skills_dir, branch)
    # Check if it's a valid Fable skill branch with a SKILL.md
    if os.path.isdir(branch_path) and "SKILL.md" in os.listdir(branch_path):
        try:
            # Dynamically import the run.py file in that folder
            module = importlib.import_module(f"skills.{branch}.run")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if hasattr(attr, "invoke"): # If it's a LangChain @tool
                    jarvis_tools.append(attr)
                    tool_map[attr.name] = attr
        except Exception as e:
            print(f"Failed to load skill {branch}: {e}")

llm_with_tools = llm.bind_tools(jarvis_tools)

def ask_gemini(user_input: str) -> str:
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_input)]
    response = llm_with_tools.invoke(messages)
    
    if response.tool_calls:
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            if name in tool_map:
                result = tool_map[name].invoke(args)
                return str(result)
                
    if isinstance(response.content, list):
        return " ".join([b.get("text", "") for b in response.content if isinstance(b, dict) and "text" in b]).strip()
    return str(response.content)