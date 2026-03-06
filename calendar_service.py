"""
Google Calendar Service
========================
Wraps the Google Calendar API.
Uses OAuth2 refresh token stored as an env variable (no re-auth needed).
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TIMEZONE = "Asia/Taipei"
CALENDAR_ID = "primary"


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


def _to_rfc3339(dt_str: str) -> str:
    """Convert ISO datetime string to RFC3339 with timezone."""
    tz = ZoneInfo(TIMEZONE)
    # Handle both date-only and datetime strings
    if "T" in dt_str:
        dt = datetime.fromisoformat(dt_str)
    else:
        dt = datetime.fromisoformat(f"{dt_str}T00:00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.isoformat()


def create_event(title: str, start: str, end: str, description: str = "") -> dict:
    service = _get_service()
    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": _to_rfc3339(start), "timeZone": TIMEZONE},
        "end":   {"dateTime": _to_rfc3339(end),   "timeZone": TIMEZONE},
    }
    return service.events().insert(calendarId=CALENDAR_ID, body=event).execute()


def get_events(start_date: str, end_date: str) -> list:
    service = _get_service()
    result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=_to_rfc3339(start_date),
        timeMax=_to_rfc3339(end_date),
        singleEvents=True,
        orderBy="startTime",
        maxResults=20,
    ).execute()
    return result.get("items", [])


def update_event(event_id: str, title: str = None, start: str = None,
                 end: str = None, description: str = None) -> dict:
    service = _get_service()
    event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
    if title:
        event["summary"] = title
    if start:
        event["start"] = {"dateTime": _to_rfc3339(start), "timeZone": TIMEZONE}
    if end:
        event["end"] = {"dateTime": _to_rfc3339(end), "timeZone": TIMEZONE}
    if description is not None:
        event["description"] = description
    return service.events().update(
        calendarId=CALENDAR_ID, eventId=event_id, body=event
    ).execute()


def delete_event(event_id: str) -> bool:
    service = _get_service()
    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    return True
