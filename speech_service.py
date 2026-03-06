"""
Google Speech-to-Text Service
==============================
Converts LINE audio messages (m4a) to text using Google Speech-to-Text.
Uses ffmpeg subprocess directly to avoid pydub/pyaudioop dependency.
"""

import io
import os
import subprocess
import tempfile

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.cloud import speech

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/cloud-platform",
]


def _get_credentials():
    creds = Credentials(
        token=None,
        refresh_token=os.environ.get("GOOGLE_REFRESH_TOKEN"),
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def transcribe_audio(audio_bytes: bytes) -> str:
    """Convert m4a audio bytes to text using ffmpeg + Google Speech-to-Text."""
    m4a_file = None
    flac_file = None
    try:
        # Write m4a to temp file
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            f.write(audio_bytes)
            m4a_file = f.name

        flac_file = m4a_file.replace(".m4a", ".flac")

        # Convert m4a → FLAC (mono, 16kHz) via ffmpeg
        subprocess.run(
            ["ffmpeg", "-y", "-i", m4a_file, "-ar", "16000", "-ac", "1", flac_file],
            check=True,
            capture_output=True,
        )

        with open(flac_file, "rb") as f:
            flac_bytes = f.read()

        client = speech.SpeechClient(credentials=_get_credentials())
        response = client.recognize(
            config=speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
                sample_rate_hertz=16000,
                language_code="zh-TW",
                alternative_language_codes=["en-US"],
            ),
            audio=speech.RecognitionAudio(content=flac_bytes),
        )

        texts = [result.alternatives[0].transcript for result in response.results]
        return " ".join(texts) if texts else ""

    finally:
        if m4a_file and os.path.exists(m4a_file):
            os.unlink(m4a_file)
        if flac_file and os.path.exists(flac_file):
            os.unlink(flac_file)
