#!/usr/bin/env python3
"""One-time helper: mint a YouTube refresh token for the headless pipeline.

The GitHub Action uploads with *no browser* (refresh-token flow), so you
do this ONCE on your laptop, then paste the printed value into the
`YOUTUBE_REFRESH_TOKEN` GitHub secret. Requires a local browser for the
Google consent screen.

Prereqs:
    pip install google-auth-oauthlib google-api-python-client
    YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET in backend/.env (or env vars),
    and http://localhost:8080/ registered as an authorized redirect URI
    in your Google Cloud OAuth client.

Run:
    env -u PYTHONPATH ./.venv/Scripts/python.exe scripts/yt_token.py
"""

from __future__ import annotations

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]

CLIENT_CONFIG = {
    "installed": {
        "client_id": os.environ.get("YOUTUBE_CLIENT_ID", ""),
        "client_secret": os.environ.get("YOUTUBE_CLIENT_SECRET", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080"],
    }
}


def main() -> int:
    if not CLIENT_CONFIG["installed"]["client_id"]:
        print("Error: set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET first "
              "(backend/.env or environment).", file=sys.stderr)
        return 1
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent")
    if not creds.refresh_token:
        print("Error: no refresh_token returned (approve while signed in as the "
              "uploading channel). Try again and grant access.", file=sys.stderr)
        return 1
    print("\n=== YOUTUBE_REFRESH_TOKEN (add this as a GitHub secret) ===")
    print(creds.refresh_token)
    print("=== END ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())