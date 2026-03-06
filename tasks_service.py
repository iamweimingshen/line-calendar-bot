"""
Google Tasks Service
=====================
Wraps the Google Tasks API.
Uses the same OAuth2 refresh token as calendar_service.
"""

import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TASKLIST = "@default"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/tasks",
]


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("tasks", "v1", credentials=creds)


def create_task(title: str, notes: str = "", due: str = "") -> dict:
    """Create a new task. due is an RFC 3339 date string (e.g. 2026-03-07T00:00:00Z)."""
    service = _get_service()
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due if due.endswith("Z") else due + "Z"
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
