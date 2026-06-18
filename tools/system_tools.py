from langchain_core.tools import tool
import webbrowser
import subprocess
import requests
import pywhatkit
from config.settings import OPENWEATHER_API_KEY, NEWS_API_KEY

@tool
def open_website(site_name: str) -> str:
    """Opens a general website. Do NOT use this for playing specific music or videos."""
    urls = {
        "google": "https://www.google.com",
        "github": "https://github.com"
    }
    url = urls.get(site_name.lower(), f"https://www.{site_name}.com")
    webbrowser.open(url)
    return f"I have opened {site_name}."

@tool
def play_on_youtube(query: str) -> str:
    """Plays a specific video, song, or movie trailer on YouTube. Use this when the user asks to play something."""
    print(f"\n[*] Searching and playing '{query}' on YouTube...")
    pywhatkit.playonyt(query)
    return f"I am playing {query} on YouTube right now."

@tool
def get_weather(city: str) -> str:
    """Gets the current weather and temperature for a specific city."""
    if not OPENWEATHER_API_KEY:
        return "Weather API key is missing."
        
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        response = requests.get(url).json()
        temp = response['main']['temp']
        desc = response['weather'][0]['description']
        return f"The weather in {city} is currently {temp}°C with {desc}."
    except Exception:
        return f"I couldn't fetch the weather for {city} right now."

@tool
def get_news(topic: str = "technology") -> str:
    """Gets the top 3 latest news headlines for a given topic."""
    if not NEWS_API_KEY:
        return "News API key is missing."
        
    url = f"https://newsapi.org/v2/top-headlines?q={topic}&apiKey={NEWS_API_KEY}&language=en&pageSize=3"
    try:
        response = requests.get(url).json()
        articles = response.get('articles', [])
        if not articles:
            return f"I couldn't find any recent news about {topic}."
            
        headlines = [article['title'] for article in articles]
        return f"Here is the latest {topic} news: 1. {headlines[0]}. 2. {headlines[1]}. 3. {headlines[2]}."
    except Exception:
        return "I encountered an error while fetching the news."

@tool
def shutdown_system() -> str:
    """Shuts down the Windows operating system."""
    print("\n[*] WARNING: System shutdown sequence triggered.")
    # subprocess.run(["shutdown", "/s", "/t", "30"]) 
    return "System shutdown sequence initiated."