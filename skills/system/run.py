from langchain_core.tools import tool
import sys

@tool
def shutdown_system() -> str:
    """Triggers the system shutdown sequence."""
    print("[*] Terminating Jarvis OS...")
    sys.exit(0)