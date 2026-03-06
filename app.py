"""
Line Calendar Bot — Main Server
================================
FastAPI server that receives Line webhook events,
processes them with Claude, and replies via Line Messaging API.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import claude_service

app = FastAPI()

LINE_CHANNEL_SECRET      = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_USER_ID             = os.environ.get("LINE_USER_ID", "")  # security: only respond to Brian

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser        = WebhookParser(LINE_CHANNEL_SECRET)


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
        if not isinstance(event.message, TextMessageContent):
            continue

        # Security: only respond to Brian
        if LINE_USER_ID and event.source.user_id != LINE_USER_ID:
            continue

        asyncio.create_task(
            _handle_message(event.message.text, event.reply_token)
        )

    return {"status": "ok"}


async def _handle_message(user_message: str, reply_token: str):
    try:
        reply = await claude_service.process_message(user_message)
    except Exception as e:
        reply = f"❌ Error: {e}"

    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=reply[:5000])],
            )
        )
