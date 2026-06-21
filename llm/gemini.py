from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from llm.prompts import SYSTEM_PROMPT
from config.settings import GOOGLE_API_KEY

# In gemini.py
from skills.system_tools import open_website, play_on_youtube, get_weather, get_news, shutdown_system

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.7
)

# Added the new tools to the list
jarvis_tools = [open_website, play_on_youtube, get_weather, get_news, shutdown_system]
llm_with_tools = llm.bind_tools(jarvis_tools)

import sys

def ask_gemini(user_input: str) -> str:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input)
    ]
    
    response = llm_with_tools.invoke(messages)
    
    # 1. Handle Tool Calls
    if response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            tool_map = {
                "open_website": open_website,
                "play_on_youtube": play_on_youtube,
                "get_weather": get_weather,
                "get_news": get_news,
                "shutdown_system": shutdown_system
            }
            
            if tool_name in tool_map:
                result = tool_map[tool_name].invoke(tool_args)
                
                # If Gemini decides to shut down, terminate the loop instantly
                if tool_name == "shutdown_system":
                    print("[*] Terminating Jarvis OS...")
                    sys.exit(0)
                    
                return str(result)
                
    # 2. Extract plain text from the new LangChain/Gemini List format
    if isinstance(response.content, list):
        # Loops through the JSON array and extracts only the 'text' values
        clean_text = " ".join([block.get("text", "") for block in response.content if isinstance(block, dict) and "text" in block])
        return clean_text.strip()
        
    # Fallback for standard string responses
    return str(response.content)