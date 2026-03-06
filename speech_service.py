"""
Google Speech-to-Text Service
==============================
Converts LINE audio messages (m4a) to text using Google Cloud Speech-to-Text.
"""

import io
import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.cloud import speech
from pydub import AudioSegment

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
    """Convert m4a audio bytes to text."""
    # Convert m4a to FLAC (mono, 16kHz) for Google STT
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="m4a")
    audio = audio.set_channels(1).set_frame_rate(16000)

    flac_buffer = io.BytesIO()
    audio.export(flac_buffer, format="flac")

    client = speech.SpeechClient(credentials=_get_credentials())
    response = client.recognize(
        config=speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.FLAC,
            sample_rate_hertz=16000,
            language_code="zh-TW",
            alternative_language_codes=["en-US"],
        ),
        audio=speech.RecognitionAudio(content=flac_buffer.getvalue()),
    )

    texts = [result.alternatives[0].transcript for result in response.results]
    return " ".join(texts) if texts else ""
