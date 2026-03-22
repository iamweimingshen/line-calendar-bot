"""
Line Calendar Bot — Main Server
================================
FastAPI server that receives Line webhook events,
processes them with Claude, and replies via Line Messaging API.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Configure logging before anything else so all modules inherit it
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, AudioMessageContent

import claude_service
import speech_service
from scheduler import create_scheduler

# ── Startup validation ────────────────────────────────────────────────────────
_REQUIRED_ENV = [
    "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_USER_ID",
    "ANTHROPIC_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
]

def _validate_env():
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

_validate_env()

LINE_CHANNEL_SECRET       = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID              = os.environ["LINE_USER_ID"]

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser        = WebhookParser(LINE_CHANNEL_SECRET)

# Reply token is only valid for 30 seconds — leave 5s margin
_REPLY_TIMEOUT = 25.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LINE Calendar Bot")
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()
    logger.info("LINE Calendar Bot stopped")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health():
    return {"status": "ok", "service": "line-calendar-bot"}


@app.post("/webhook")
async def webhook(request: Request):
    body      = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    try:
        events = parser.parse(body.decode(), signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        # Fail-secure: reject any user that isn't the configured owner
        if event.source.user_id != LINE_USER_ID:
            continue

        user_id = event.source.user_id

        if isinstance(event.message, TextMessageContent):
            task = asyncio.create_task(
                _handle_message(event.message.text, event.reply_token, user_id)
            )
            task.add_done_callback(_log_task_exception)
        elif isinstance(event.message, AudioMessageContent):
            task = asyncio.create_task(
                _handle_audio(event.message.id, event.reply_token, user_id)
            )
            task.add_done_callback(_log_task_exception)

    return {"status": "ok"}


def _log_task_exception(task: asyncio.Task):
    """Log any unhandled exception from a fire-and-forget task."""
    if not task.cancelled() and task.exception():
        logger.exception("Unhandled exception in background task", exc_info=task.exception())


async def _handle_message(user_message: str, reply_token: str, user_id: str):
    try:
        reply = await asyncio.wait_for(
            claude_service.process_message(user_message, user_id),
            timeout=_REPLY_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Message processing timed out for user %s", user_id)
        reply = "⏱ 處理時間過長，請稍後再試。"
    except Exception as e:
        logger.exception("Error processing message for user %s", user_id)
        if "invalid_grant" in str(e).lower():
            reply = "⚠️ Google 授權已過期，請通知管理員重新授權。"
        else:
            reply = "❌ 發生錯誤，請稍後再試。"

    await _reply(reply_token, reply)


async def _handle_audio(message_id: str, reply_token: str, user_id: str):
    try:
        async with AsyncApiClient(configuration) as api_client:
            blob_api = AsyncMessagingApiBlob(api_client)
            audio_bytes = await blob_api.get_message_content(message_id)

        text = await asyncio.wait_for(
            asyncio.to_thread(speech_service.transcribe_audio, audio_bytes),
            timeout=15.0,
        )
        if not text:
            await _reply(reply_token, "❌ 無法辨識語音，請再說一次或改用文字。")
            return

        reply = await asyncio.wait_for(
            claude_service.process_message(text, user_id),
            timeout=_REPLY_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Audio processing timed out for user %s", user_id)
        reply = "⏱ 處理時間過長，請改用文字。"
    except Exception as e:
        logger.exception("Error processing audio for user %s", user_id)
        if "invalid_grant" in str(e).lower():
            reply = "⚠️ Google 授權已過期，請通知管理員重新授權。"
        else:
            reply = "❌ 語音處理失敗，請稍後再試或改用文字。"

    await _reply(reply_token, reply)


async def _reply(reply_token: str, text: str):
    try:
        async with AsyncApiClient(configuration) as api_client:
            api = AsyncMessagingApi(api_client)
            await api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text[:5000])],
                )
            )
    except Exception:
        logger.exception("Failed to send LINE reply")
