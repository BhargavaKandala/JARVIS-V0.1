# skills/calendar_tools.py
import os
import datetime
from langchain_core.tools import tool
from config.settings import GOOGLE_CALENDAR_CREDENTIALS_PATH, GOOGLE_CALENDAR_TOKEN_PATH

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

_service = None


def _get_service():
    """Builds (and caches) the Calendar API client. Runs the one-time OAuth consent flow
    on first use if no cached token exists. Requires google-api-python-client,
    google-auth-httplib2, and google-auth-oauthlib to be installed."""
    global _service
    if _service is not None:
        return _service

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(GOOGLE_CALENDAR_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GOOGLE_CALENDAR_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GOOGLE_CALENDAR_CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"No Google Calendar credentials found at {GOOGLE_CALENDAR_CREDENTIALS_PATH}. "
                    "Download an OAuth client JSON from Google Cloud Console and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CALENDAR_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(GOOGLE_CALENDAR_TOKEN_PATH), exist_ok=True)
        with open(GOOGLE_CALENDAR_TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    _service = build("calendar", "v3", credentials=creds)
    return _service


def list_upcoming_events(max_results: int = 5) -> list:
    """Plain function: returns the next upcoming calendar events. Returns [] on any error
    (e.g. not configured yet) so callers can degrade gracefully."""
    try:
        service = _get_service()
        now = datetime.datetime.utcnow().isoformat() + "Z"
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return events_result.get("items", [])
    except Exception:
        return []


@tool
def get_calendar_events(max_results: int = 5) -> str:
    """Gets the user's next upcoming Google Calendar events."""
    events = list_upcoming_events(max_results)
    if not events:
        return "I couldn't find any upcoming calendar events (or the calendar isn't connected yet)."

    lines = []
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        lines.append(f"- {event.get('summary', 'Untitled event')} at {start}")
    return "Here's what's coming up:\n" + "\n".join(lines)
