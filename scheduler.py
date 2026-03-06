"""
Scheduler Service
==================
Background jobs:
- Every 5 mins: self-ping to prevent Render from sleeping
- 7am daily morning briefing (today + tomorrow events)
- Every minute: push reminder 15 mins before events
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    PushMessageRequest,
    TextMessage,
)

import calendar_service

TIMEZONE = ZoneInfo("Asia/Taipei")

LINE_USER_ID              = os.environ.get("LINE_USER_ID", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
SELF_URL                  = os.environ.get("RENDER_EXTERNAL_URL", "")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

_reminded_event_ids: set = set()


async def self_ping():
    """Ping our own health endpoint every 5 mins to prevent Render from sleeping."""
    if not SELF_URL:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{SELF_URL}/", timeout=10)
    except Exception:
        pass


async def _push(message: str):
    async with AsyncApiClient(configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        await api.push_message(
            PushMessageRequest(
                to=LINE_USER_ID,
                messages=[TextMessage(text=message[:5000])],
            )
        )


async def morning_briefing():
    """7:00 AM — send events for today and tomorrow (full days)."""
    now = datetime.now(TIMEZONE)
    today_start  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + timedelta(days=2)  # end of tomorrow = start of day after

    try:
        events = calendar_service.get_events(
            start_date=today_start.isoformat(),
            end_date=tomorrow_end.isoformat(),
        )
    except Exception as e:
        await _push(f"☀️ 早安 Brian！取得行程失敗：{e}")
        return

    if not events:
        await _push("☀️ 早安 Brian！今明兩天沒有行程，放鬆一下！")
        return

    lines = ["☀️ 早安 Brian！今明兩天的行程：\n"]
    for e in events:
        start = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date", "")
        if "T" in start:
            dt = datetime.fromisoformat(start).astimezone(TIMEZONE)
            time_str = dt.strftime("%m/%d (%a) %H:%M")
        else:
            time_str = start
        lines.append(f"📅 {e.get('summary', '(no title)')} — {time_str}")

    await _push("\n".join(lines))


async def check_upcoming_reminders():
    """Every minute — push reminder if an event starts in ~15 minutes."""
    now = datetime.now(TIMEZONE)
    target = now + timedelta(minutes=15)

    window_start = target - timedelta(seconds=30)
    window_end   = target + timedelta(seconds=30)

    try:
        events = calendar_service.get_events(
            start_date=window_start.isoformat(),
            end_date=window_end.isoformat(),
        )
    except Exception:
        return

    for event in events:
        event_id = event.get("id")
        if not event_id or event_id in _reminded_event_ids:
            continue

        _reminded_event_ids.add(event_id)
        title    = event.get("summary", "(no title)")
        start    = (event.get("start") or {}).get("dateTime", "")
        time_str = ""
        if "T" in start:
            dt = datetime.fromisoformat(start).astimezone(TIMEZONE)
            time_str = dt.strftime("%H:%M")

        await _push(f"⏰ 提醒：《{title}》15 分鐘後開始（{time_str}）")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        self_ping,
        trigger="interval",
        minutes=5,
        id="self_ping",
    )

    scheduler.add_job(
        morning_briefing,
        trigger="cron",
        hour=7,
        minute=0,
        id="morning_briefing",
    )

    scheduler.add_job(
        check_upcoming_reminders,
        trigger="interval",
        minutes=1,
        id="reminder_check",
    )

    return scheduler
