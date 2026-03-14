"""
Google OAuth2 Shared Credentials
==================================
Provides a single cached credential object shared by calendar, tasks,
and speech services. Token is only refreshed when expired (~1 hr).
"""

import os
import threading

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# All scopes needed across all services
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/tasks",
]

_creds_cache: Credentials | None = None
_creds_lock = threading.Lock()


def get_credentials() -> Credentials:
    """Return a valid (refreshed if necessary) Google OAuth2 credential."""
    global _creds_cache
    with _creds_lock:
        if _creds_cache is not None and _creds_cache.valid:
            return _creds_cache

        creds = Credentials(
            token=None,
            refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
            client_id=os.environ.get("GOOGLE_CLIENT_ID"),
            client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        creds.refresh(Request())
        _creds_cache = creds
        return creds
