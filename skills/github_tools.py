# skills/github_tools.py
import requests
from langchain_core.tools import tool
from config.settings import GITHUB_TOKEN

GITHUB_API = "https://api.github.com"


def _headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def list_open_issues(repo: str, limit: int = 5) -> list:
    """Plain function: returns open issues (excluding PRs) for 'owner/repo'. Returns [] on any error."""
    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers=_headers(),
            params={"state": "open", "per_page": limit},
            timeout=10,
        )
        response.raise_for_status()
        return [i for i in response.json() if "pull_request" not in i][:limit]
    except Exception:
        return []


def list_open_prs(repo: str, limit: int = 5) -> list:
    """Plain function: returns open pull requests for 'owner/repo'. Returns [] on any error."""
    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            headers=_headers(),
            params={"state": "open", "per_page": limit},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()[:limit]
    except Exception:
        return []


def get_recent_commit_activity(repo: str, limit: int = 5) -> list:
    """Plain function: returns the most recent commits on the default branch for 'owner/repo'. Returns [] on any error."""
    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{repo}/commits",
            headers=_headers(),
            params={"per_page": limit},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()[:limit]
    except Exception:
        return []


@tool
def get_github_repo_status(repo: str) -> str:
    """Gets a summary of open issues, open PRs, and recent commit activity for a GitHub repo (format: 'owner/repo')."""
    issues = list_open_issues(repo)
    prs = list_open_prs(repo)
    commits = get_recent_commit_activity(repo, limit=1)

    parts = [f"{repo}: {len(issues)} open issue(s), {len(prs)} open PR(s)."]
    if commits:
        message = commits[0].get("commit", {}).get("message", "").splitlines()[0]
        parts.append(f"Latest commit: {message}")
    return " ".join(parts)
