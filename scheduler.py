"""
Scheduler Service
==================
Background jobs:
- Every 5 mins: self-ping to prevent Render from sleeping
- 7am daily morning briefing (today + tomorrow events)
- Every minute: push reminder 15 mins before timed events (not all-day)
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
import tasks_service

TIMEZONE = ZoneInfo("Asia/Taipei")

LINE_USER_ID              = os.environ.get("LINE_USER_ID", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
SELF_URL                  = os.environ.get("RENDER_EXTERNAL_URL", "")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# event_id -> reminded_at (datetime); pruned after 24 hours
_reminded_events: dict = {}


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
    tomorrow_end = today_start + timedelta(days=2)

    try:
        events = calendar_service.get_events(
            start_date=today_start.isoformat(),
            end_date=tomorrow_end.isoformat(),
        )
    except Exception as e:
        await _push(f"☀️ 早安 Brian！取得行程失敗：{e}")
        return

    # Fetch incomplete tasks
    try:
        tasks = tasks_service.get_tasks(include_completed=False)
    except Exception:
        tasks = []

    if not events and not tasks:
        await _push("☀️ 早安 Brian！今明兩天沒有行程，也沒有待辦事項，放鬆一下！")
        return

    lines = ["☀️ 早安 Brian！\n"]

    if events:
        lines.append("📅 今明兩天的行程：")
        for e in events:
            start = (e.get("start") or {})
            if "dateTime" in start:
                dt = datetime.fromisoformat(start["dateTime"]).astimezone(TIMEZONE)
                time_str = dt.strftime("%m/%d (%a) %H:%M")
            else:
                time_str = f"{start.get('date', '')} (整天)"
            lines.append(f"  • {e.get('summary', '(no title)')} — {time_str}")
    else:
        lines.append("📅 今明兩天沒有行程")

    if tasks:
        lines.append("\n☐ 待辦事項：")
        for t in tasks:
            due = f"（期限 {t['due'][:10]}）" if t.get("due") else ""
            lines.append(f"  • {t.get('title', '(no title)')}{due}")
    else:
        lines.append("\n☐ 沒有待辦事項")

    await _push("\n".join(lines))


async def check_upcoming_reminders():
    """Every minute — push reminder if a TIMED event starts in ~15 minutes.
    All-day events are skipped (already shown in morning briefing).
    """
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

    # Prune entries older than 24 hours to prevent unbounded growth
    cutoff = now - timedelta(hours=24)
    expired = [k for k, v in _reminded_events.items() if v < cutoff]
    for k in expired:
        del _reminded_events[k]

    for event in events:
        # Skip all-day events — no dateTime means it's a full-day event
        if "dateTime" not in (event.get("start") or {}):
            continue

        event_id = event.get("id")
        if not event_id or event_id in _reminded_events:
            continue

        _reminded_events[event_id] = now
        title    = event.get("summary", "(no title)")
        dt       = datetime.fromisoformat(event["start"]["dateTime"]).astimezone(TIMEZONE)
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
