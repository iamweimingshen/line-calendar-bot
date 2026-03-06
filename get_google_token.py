"""
Google OAuth2 Token Helper
===========================
Run this script ONCE locally to get your refresh token.
Then save the token to your .env / Render environment variables.

Usage:
  python get_google_token.py
"""

import os
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/tasks",
]


def main():
    client_id     = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env first.")
        return

    client_config = {
        "installed": {
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
            "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
            "token_uri":     "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n✅ Authentication successful!\n")
    print("Add this to your .env and Render environment variables:")
    print(f"\nGOOGLE_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    main()
