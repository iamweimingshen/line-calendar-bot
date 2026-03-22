"""
Google Tasks Service
=====================
Wraps the Google Tasks API.
Uses the same OAuth2 refresh token as calendar_service.
"""

from googleapiclient.discovery import build
import google_auth

TASKLIST = "@default"


def _get_service():
    return build("tasks", "v1", credentials=google_auth.get_credentials())


def create_task(title: str, notes: str = "", due: str = "") -> dict:
    """Create a new task. due is an RFC 3339 date string (e.g. 2026-03-07T00:00:00Z)."""
    service = _get_service()
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        # Normalise to RFC3339 UTC: strip any tz offset and append Z
        if "T" not in due:
            due = due + "T00:00:00Z"
        elif due.endswith("Z"):
            pass  # already correct
        elif "+" in due[10:] or due.count("-") > 2:
            # Has offset like +08:00 — convert to UTC naive then add Z
            from datetime import timezone as _tz
            from datetime import datetime as _dt
            due = _dt.fromisoformat(due).astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            due = due + "Z"
        body["due"] = due
    return service.tasks().insert(tasklist=TASKLIST, body=body).execute()


def get_tasks(include_completed: bool = False) -> list:
    """Get tasks. By default only returns incomplete tasks."""
    service = _get_service()
    result = service.tasks().list(
        tasklist=TASKLIST,
        showCompleted=include_completed,
        showHidden=include_completed,
        maxResults=20,
    ).execute()
    return result.get("items", [])


def complete_task(task_id: str) -> dict:
    """Mark a task as completed."""
    service = _get_service()
    task = service.tasks().get(tasklist=TASKLIST, task=task_id).execute()
    task["status"] = "completed"
    return service.tasks().update(tasklist=TASKLIST, task=task_id, body=task).execute()


def delete_task(task_id: str) -> bool:
    """Delete a task."""
    service = _get_service()
    service.tasks().delete(tasklist=TASKLIST, task=task_id).execute()
    return True
