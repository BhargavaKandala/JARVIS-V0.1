from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from llm.prompts import SYSTEM_PROMPT
from config.settings import GOOGLE_API_KEY
from tools.system_tools import open_website, play_on_youtube, get_weather, get_news, shutdown_system

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.7
)

# Added the new tools to the list
jarvis_tools = [open_website, play_on_youtube, get_weather, get_news, shutdown_system]
llm_with_tools = llm.bind_tools(jarvis_tools)

def ask_gemini(user_input: str) -> str:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input)
    ]
    
    response = llm_with_tools.invoke(messages)
    
    if response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # Map the LLM's decision to the actual Python function
            tool_map = {
                "open_website": open_website,
                "play_on_youtube": play_on_youtube,
                "get_weather": get_weather,
                "get_news": get_news,
                "shutdown_system": shutdown_system
            }
            
            if tool_name in tool_map:
                return tool_map[tool_name].invoke(tool_args)
                
    return str(response.content)