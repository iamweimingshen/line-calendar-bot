"""
Claude NLP Service
==================
Uses Claude Sonnet 4.6 with tool use to understand natural language
and translate it into Google Calendar operations.

Conversation memory: keeps last 5 rounds per user.
Resets if the user has been inactive for more than 10 minutes.
"""

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import anthropic
import calendar_service

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

TIMEZONE = ZoneInfo("Asia/Taipei")
MEMORY_TIMEOUT = timedelta(minutes=10)
MAX_ROUNDS = 5  # keep last 5 rounds (user + assistant pairs)

# Per-user conversation state: { user_id: {"history": [...], "last_active": datetime} }
_conversations: dict[str, dict] = {}

TOOLS = [
    {
        "name": "create_event",
        "description": "Create a new calendar event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Event title"},
                "start":       {"type": "string", "description": "Start datetime (ISO format, e.g. 2026-03-05T14:00:00)"},
                "end":         {"type": "string", "description": "End datetime (ISO format)"},
                "description": {"type": "string", "description": "Optional notes or details"},
            },
            "required": ["title", "start", "end"],
        },
    },
    {
        "name": "get_events",
        "description": "Get calendar events within a date/time range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start of range (ISO format, e.g. 2026-03-05 or 2026-03-05T00:00:00)"},
                "end_date":   {"type": "string", "description": "End of range (ISO format)"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "update_event",
        "description": "Update an existing event. Use get_events first to find the event_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id":    {"type": "string", "description": "Google Calendar event ID"},
                "title":       {"type": "string", "description": "New title (optional)"},
                "start":       {"type": "string", "description": "New start datetime (optional)"},
                "end":         {"type": "string", "description": "New end datetime (optional)"},
                "description": {"type": "string", "description": "New notes (optional)"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_event",
        "description": "Delete a calendar event. Use get_events first to find the event_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Google Calendar event ID to delete"},
            },
            "required": ["event_id"],
        },
    },
]


def _system_prompt() -> str:
    today = date.today().strftime("%Y-%m-%d (%A)")
    return f"""You are Brian's personal calendar assistant on LINE.
Brian is in Taipei, Taiwan (UTC+8). Today is {today}.

Rules:
- Reply in the same language Brian uses (English or Traditional Chinese)
- Be concise — this is a mobile chat interface

Creating events:
- If the date is missing or unclear, ask before creating
- If the time is missing or unclear, ask before creating
- Default duration: 1 hour if not specified (no need to ask)

Deleting or updating events:
- Always call get_events first to find matching events
- If multiple events match, list them and ask which one to act on
- If exactly one event matches, briefly confirm the title and time, then proceed
- Never delete or update without showing what you found first

General:
- Ask at most ONE clarifying question at a time
- Never take irreversible actions (delete/update) without confirmation"""


def _get_history(user_id: str) -> list:
    """Return conversation history, reset if inactive for > 10 minutes."""
    now = datetime.now(TIMEZONE)
    state = _conversations.get(user_id)

    if state and (now - state["last_active"]) <= MEMORY_TIMEOUT:
        return state["history"]

    # New conversation or timed out — start fresh
    _conversations[user_id] = {"history": [], "last_active": now}
    return []


def _save_history(user_id: str, user_msg: str, assistant_msg: str):
    """Append this round to history, keeping only the last MAX_ROUNDS rounds."""
    now = datetime.now(TIMEZONE)
    state = _conversations[user_id]
    state["last_active"] = now

    state["history"].append({"role": "user",      "content": user_msg})
    state["history"].append({"role": "assistant",  "content": assistant_msg})

    # Keep only the last MAX_ROUNDS rounds (each round = 2 messages)
    max_messages = MAX_ROUNDS * 2
    if len(state["history"]) > max_messages:
        state["history"] = state["history"][-max_messages:]


async def process_message(user_message: str, user_id: str = "default") -> str:
    history = _get_history(user_id)
    messages = history + [{"role": "user", "content": user_message}]

    # Agentic loop — let Claude call tools until done
    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_system_prompt(),
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            texts = [b.text for b in response.content if b.type == "text"]
            reply = texts[0] if texts else "Done."
            _save_history(user_id, user_message, reply)
            return reply

        if response.stop_reason != "tool_use":
            return "Sorry, something went wrong. Please try again."

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = _execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            except Exception as e:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Error: {e}",
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})


def _execute_tool(name: str, inputs: dict) -> str:
    if name == "create_event":
        event = calendar_service.create_event(**inputs)
        return f"Created: {event.get('id')} — {event.get('summary')}"

    if name == "get_events":
        events = calendar_service.get_events(**inputs)
        if not events:
            return "No events found in this period."
        lines = []
        for e in events:
            start = (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date", "")
            lines.append(f"[{e['id']}] {e.get('summary', '(no title)')} @ {start}")
        return "\n".join(lines)

    if name == "update_event":
        event = calendar_service.update_event(**inputs)
        return f"Updated: {event.get('summary')}"

    if name == "delete_event":
        calendar_service.delete_event(**inputs)
        return "Deleted successfully."

    return f"Unknown tool: {name}"
