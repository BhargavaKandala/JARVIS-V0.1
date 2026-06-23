# skills/memory_tools.py
import requests
import os
import urllib3
import urllib.parse
from dotenv import load_dotenv
from langchain_core.tools import tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

OBSIDIAN_API_KEY = os.getenv("OBSIDIAN_API_KEY")
# Strip trailing slashes to prevent //vault/ 404 errors
OBSIDIAN_URL = os.getenv("OBSIDIAN_URL", "https://127.0.0.1:27124").rstrip('/')

HEADERS = {
    "Authorization": f"Bearer {OBSIDIAN_API_KEY}",
    "Content-Type": "text/markdown"
}

@tool
def save_memory(filename: str, content: str) -> str:
    """Saves a new memory, note, preference, or idea to the Obsidian vault."""
    # Ensure no double .md extensions and encode spaces properly
    clean_name = filename.replace(".md", "").strip() + ".md"
    safe_filename = urllib.parse.quote(clean_name)
    
    url = f"{OBSIDIAN_URL}/vault/{safe_filename}"
    try:
        response = requests.put(url, headers=HEADERS, data=content.encode('utf-8'), verify=False)
        if response.status_code in [200, 201, 204]:
            return f"Successfully saved memory to {clean_name}"
        return f"Failed to save: {response.text} (Status Code: {response.status_code})"
    except Exception as e:
        return f"Error connecting to Obsidian: {str(e)}"

@tool
def read_memory(filename: str) -> str:
    """Reads a specific memory or note from the Obsidian vault."""
    clean_name = filename.replace(".md", "").strip() + ".md"
    safe_filename = urllib.parse.quote(clean_name)
    
    url = f"{OBSIDIAN_URL}/vault/{safe_filename}"
    try:
        response = requests.get(url, headers=HEADERS, verify=False)
        if response.status_code == 200:
            return response.text
        return f"Memory not found. Status Code: {response.status_code}"
    except Exception as e:
        return f"Error connecting to Obsidian: {str(e)}"