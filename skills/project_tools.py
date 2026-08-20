# skills/project_tools.py
from datetime import date, timedelta
from langchain_core.tools import tool
from memory import store
from skills.system_tools import get_weather
from skills.calendar_tools import list_upcoming_events
from skills.github_tools import list_open_issues


@tool
def create_project(name: str, priority: str = "medium", deadline: str = "") -> str:
    """Creates a new project to track (status, priority, deadline, tasks)."""
    fields = {"priority": priority}
    if deadline:
        fields["deadline"] = deadline
    store.upsert_project(name, **fields)
    return f"Created project '{name}'."


@tool
def update_project_status(name: str, status: str = "", progress_pct: int = -1, next_task: str = "") -> str:
    """Updates a project's status ('active'/'paused'/'done'/'archived'), progress percentage, and/or next task."""
    if store.get_project(name) is None:
        store.upsert_project(name)

    fields = {}
    if status:
        fields["status"] = status
    if progress_pct >= 0:
        fields["progress_pct"] = progress_pct
    if next_task:
        fields["next_task"] = next_task

    if not fields:
        return f"No changes given for '{name}'."

    store.upsert_project(name, **fields)
    return f"Updated '{name}': {fields}"


@tool
def add_project_task(project_name: str, title: str, due_date: str = "") -> str:
    """Adds an open task to a project, optionally with a due date (YYYY-MM-DD)."""
    store.add_task(project_name, title, due_date=due_date or None)
    return f"Added task '{title}' to {project_name}" + (f" (due {due_date})" if due_date else "")


@tool
def complete_project_task(project_name: str, task_title: str) -> str:
    """Marks a project's task as completed by (partial) title match."""
    task = store.find_open_task_by_title(project_name, task_title)
    if not task:
        return f"I couldn't find an open task matching '{task_title}' in {project_name}."
    store.complete_task(task["id"])
    return f"Marked '{task['title']}' as done in {project_name}."


@tool
def remember_commitment(commitment: str, due_date: str, project_name: str = "General") -> str:
    """Remembers something the user committed to doing by a specific date (YYYY-MM-DD), so it can be
    followed up on later (e.g. surfaced as overdue if not completed by then)."""
    store.add_task(project_name, commitment, due_date=due_date, source_text=commitment)
    return f"I'll remember: {commitment}, due {due_date}."


@tool
def get_project_status(name: str) -> str:
    """Gets a formatted status summary for a project: progress, priority, current task, deadline, and pending issues."""
    project = store.get_project(name)
    if not project:
        return f"I don't have a project called '{name}'."

    parts = [
        name,
        f"{project['progress_pct']}%",
        f"priority: {project['priority']}",
    ]
    if project["next_task"]:
        parts.append(f"current task: {project['next_task']}")
    if project["deadline"]:
        parts.append(f"deadline: {project['deadline']}")

    if project["github_repo"]:
        issues = list_open_issues(project["github_repo"])
        parts.append(f"pending bugs: {len(issues)}")

    return " — ".join(parts)


@tool
def list_projects_summary() -> str:
    """Lists all tracked projects with their status and progress."""
    projects = store.list_projects()
    if not projects:
        return "No projects tracked yet."
    lines = [f"- {p['name']} ({p['status']}, {p['progress_pct']}%)" for p in projects]
    return "\n".join(lines)


def build_daily_briefing() -> dict:
    """Plain function (not a tool) assembling the pieces of a daily briefing. Kept separate from the
    @tool wrapper so a future scheduler can call this directly without going through the LLM."""
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()

    open_tasks = store.list_open_tasks()
    overdue_tasks = store.list_overdue_tasks(as_of=today.isoformat())
    yesterday_log = store.get_daily_log(yesterday)

    try:
        events = list_upcoming_events(max_results=5)
    except Exception:
        events = []

    weather = None
    home_city = store.get_preference("home_city")
    if home_city:
        try:
            weather = get_weather.invoke({"city": home_city})
        except Exception:
            weather = None

    recommendation = None
    tasks_with_dates = [t for t in open_tasks if t["due_date"]]
    if tasks_with_dates:
        recommendation = sorted(tasks_with_dates, key=lambda t: t["due_date"])[0]["title"]
    elif open_tasks:
        recommendation = open_tasks[0]["title"]

    return {
        "date": today.isoformat(),
        "open_tasks": open_tasks,
        "overdue_task": overdue_tasks[0] if overdue_tasks else None,
        "calendar_events": events,
        "weather": weather,
        "yesterday_summary": yesterday_log["summary"] if yesterday_log else None,
        "recommendation": recommendation,
    }


@tool
def get_daily_briefing() -> str:
    """Gives a morning-briefing style summary: today's tasks, calendar, weather, one overdue task,
    yesterday's progress, and a recommendation. Use when the user asks about their day or wants a summary."""
    briefing = build_daily_briefing()

    lines = [f"Here's your day for {briefing['date']}."]

    if briefing["open_tasks"]:
        titles = ", ".join(t["title"] for t in briefing["open_tasks"][:5])
        lines.append(f"Open tasks: {titles}.")
    else:
        lines.append("No open tasks right now.")

    if briefing["calendar_events"]:
        lines.append(f"You have {len(briefing['calendar_events'])} calendar event(s) coming up.")

    if briefing["weather"]:
        lines.append(str(briefing["weather"]))

    if briefing["overdue_task"]:
        lines.append(f"Overdue: {briefing['overdue_task']['title']} (was due {briefing['overdue_task']['due_date']}).")

    if briefing["yesterday_summary"]:
        lines.append(f"Yesterday: {briefing['yesterday_summary']}")

    if briefing["recommendation"]:
        lines.append(f"Recommendation: focus on '{briefing['recommendation']}' first.")

    summary = " ".join(lines)
    store.upsert_daily_log(briefing["date"], summary=summary)
    return summary
