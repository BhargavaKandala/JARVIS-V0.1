from dotenv import load_dotenv
import os

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY if GOOGLE_API_KEY else ""

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- Local Hermes brain (Ollama) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
HERMES_MODEL = os.getenv("HERMES_MODEL", "hermes3:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
ENABLE_AUTO_CAPTURE = os.getenv("ENABLE_AUTO_CAPTURE", "true").lower() == "true"

_CONFIG_DIR = os.path.dirname(__file__)
_DATA_DIR = os.path.join(_CONFIG_DIR, "..", "data")

GOOGLE_CALENDAR_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CALENDAR_CREDENTIALS_PATH",
    os.path.join(_CONFIG_DIR, "google_calendar_credentials.json"),
)
GOOGLE_CALENDAR_TOKEN_PATH = os.getenv(
    "GOOGLE_CALENDAR_TOKEN_PATH",
    os.path.join(_DATA_DIR, "google_calendar_token.json"),
)

FORCE_TEXT_MODE = True