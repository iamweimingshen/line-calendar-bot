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
        # Ensure valid RFC3339 UTC format (e.g. "2026-03-07T00:00:00Z")
        if "T" not in due:
            due = due + "T00:00:00Z"
        elif not due.endswith("Z"):
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
