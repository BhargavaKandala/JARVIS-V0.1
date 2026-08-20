# skills/memory_tools.py
import requests
import os
import urllib3
import urllib.parse
from dotenv import load_dotenv
from langchain_core.tools import tool
from memory import store
from memory import vector_store

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
            result = f"Successfully saved memory to {clean_name}"
        else:
            result = f"Failed to save: {response.text} (Status Code: {response.status_code})"
    except Exception as e:
        result = f"Error connecting to Obsidian: {str(e)}"

    try:
        memory_id = store.add_memory(kind="semantic", content=content, title=clean_name, obsidian_path=clean_name)
        vector_store.index_memory(memory_id, content)
    except Exception as e:
        print(f"[memory_tools] local index write failed: {e}")

    return result

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
    except Exception:
        pass

    try:
        memory = store.find_memory_by_obsidian_path(clean_name)
        if memory:
            return memory["content"]
    except Exception as e:
        return f"Error reading local memory index: {str(e)}"

    return f"Memory '{clean_name}' not found in Obsidian or the local index."

@tool
def search_memory(query: str, top_k: int = 5) -> str:
    """Searches saved memories by meaning (not exact filename) and returns the closest matches."""
    try:
        results = vector_store.search(query, top_k=top_k)
    except Exception as e:
        return f"Error searching memory: {str(e)}"

    if not results:
        return "I couldn't find any memories matching that."

    lines = [f"- {m.get('title') or m['kind']}: {m['content'][:200]}" for m in results]
    return "Here's what I found:\n" + "\n".join(lines)

@tool
def remember_fact(fact: str, category: str = "general") -> str:
    """Quickly remembers a short fact or idea without creating an Obsidian file."""
    try:
        memory_id = store.add_memory(kind="semantic", content=fact, title=category, tags=[category])
        vector_store.index_memory(memory_id, fact)
        return f"Got it, I'll remember that: {fact}"
    except Exception as e:
        return f"Error remembering that: {str(e)}"

@tool
def remember_preference(key: str, value: str) -> str:
    """Remembers a user preference as a key/value pair (e.g. key='favorite_editor', value='VS Code')."""
    try:
        store.set_preference(key, value)
        return f"Noted: {key} = {value}"
    except Exception as e:
        return f"Error saving preference: {str(e)}"

@tool
def recall_preference(key: str) -> str:
    """Recalls a previously saved user preference by key."""
    try:
        value = store.get_preference(key)
    except Exception as e:
        return f"Error recalling preference: {str(e)}"
    if value is None:
        return f"I don't have a saved preference for '{key}'."
    return value

@tool
def log_decision(project: str, decision: str, rationale: str = "") -> str:
    """Records a decision that was made for a project, along with the reasoning."""
    try:
        store.add_decision(project, decision, rationale or None)
    except Exception as e:
        return f"Error logging decision: {str(e)}"

    try:
        content = f"Decision for {project}: {decision}" + (f" (Rationale: {rationale})" if rationale else "")
        memory_id = store.add_memory(kind="decision", content=content, title=project, tags=[project])
        vector_store.index_memory(memory_id, content)
    except Exception as e:
        print(f"[memory_tools] decision index write failed: {e}")

    return f"Logged decision for {project}: {decision}"


@tool
def get_decisions(project: str = "", limit: int = 10) -> str:
    """Lists previously logged decisions, optionally filtered to one project, most recent first.
    Use this when the user asks what was decided about something, or why a past choice was made."""
    try:
        decisions = store.list_decisions(project_name=project or None, limit=limit)
    except Exception as e:
        return f"Error retrieving decisions: {str(e)}"
    if not decisions:
        return f"No decisions logged for '{project}' yet." if project else "No decisions logged yet."
    lines = []
    for d in decisions:
        line = f"- {d['decision_text']}"
        if d["rationale"]:
            line += f" (because: {d['rationale']})"
        lines.append(line)
    return "\n".join(lines)

@tool
def get_recent_memories(kind: str = "", limit: int = 5) -> str:
    """Lists the most recently saved memories, optionally filtered by kind (semantic, daily, project, conversation_summary, preference, decision)."""
    try:
        memories = store.list_memories(kind=kind or None, limit=limit)
    except Exception as e:
        return f"Error listing memories: {str(e)}"
    if not memories:
        return "No memories found."
    lines = [f"- [{m['kind']}] {m.get('title') or ''}: {m['content'][:150]}" for m in memories]
    return "\n".join(lines)
