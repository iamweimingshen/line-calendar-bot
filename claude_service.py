"""
Claude NLP Service
==================
Uses Claude Sonnet 4.6 with tool use to understand natural language
and translate it into Google Calendar operations.
"""

import os
from datetime import date
import anthropic
import calendar_service

client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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
- Default event duration: 1 hour if not specified
- Default time: assume working hours (09:00–18:00) if time is vague
- When deleting or updating, call get_events first to find the correct event_id
- Always confirm what you did in a friendly, brief message"""


async def process_message(user_message: str) -> str:
    messages = [{"role": "user", "content": user_message}]

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
            return texts[0] if texts else "Done."

        if response.stop_reason != "tool_use":
            return "Sorry, something went wrong. Please try again."

        # Append assistant response (with tool_use blocks)
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool call
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
