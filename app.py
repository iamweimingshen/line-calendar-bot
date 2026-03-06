"""
Line Calendar Bot — Main Server
================================
FastAPI server that receives Line webhook events,
processes them with Claude, and replies via Line Messaging API.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

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

LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID              = os.environ.get("LINE_USER_ID", "")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser        = WebhookParser(LINE_CHANNEL_SECRET)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()


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

        if LINE_USER_ID and event.source.user_id != LINE_USER_ID:
            continue

        user_id = event.source.user_id

        if isinstance(event.message, TextMessageContent):
            asyncio.create_task(
                _handle_message(event.message.text, event.reply_token, user_id)
            )
        elif isinstance(event.message, AudioMessageContent):
            asyncio.create_task(
                _handle_audio(event.message.id, event.reply_token, user_id)
            )

    return {"status": "ok"}


async def _handle_message(user_message: str, reply_token: str, user_id: str):
    try:
        reply = await claude_service.process_message(user_message, user_id)
    except Exception as e:
        reply = f"❌ Error: {e}"

    await _reply(reply_token, reply)


async def _handle_audio(message_id: str, reply_token: str, user_id: str):
    try:
        async with AsyncApiClient(configuration) as api_client:
            blob_api = AsyncMessagingApiBlob(api_client)
            audio_bytes = await blob_api.get_message_content(message_id)

        text = await asyncio.to_thread(speech_service.transcribe_audio, audio_bytes)
        if not text:
            await _reply(reply_token, "❌ 無法辨識語音，請再說一次或改用文字。")
            return

        reply = await claude_service.process_message(text, user_id)
    except Exception as e:
        reply = f"❌ 語音處理失敗: {e}"

    await _reply(reply_token, reply)


async def _reply(reply_token: str, text: str):
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text[:5000])],
            )
        )
