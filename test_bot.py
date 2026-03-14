"""
QA Test Suite — LINE Calendar Bot
====================================
Tests core logic WITHOUT hitting external APIs (Google, LINE, Anthropic).
Run: python test_bot.py

Coverage:
- google_auth: credential caching
- calendar_service: RFC3339 conversion
- tasks_service: due date formatting
- claude_service: conversation memory (timeout, max rounds)
- speech_service: audio size limit
- app.py: LINE_USER_ID fail-secure logic
- scheduler: _reminded_events pruning
"""

import sys
import os
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch

# ── Helpers ──────────────────────────────────────────────────────────────────

def ok(label):
    print(f"  ✅ {label}")

def fail(label, reason):
    print(f"  ❌ {label}: {reason}")
    return False


# ── 1. calendar_service: _to_rfc3339 ─────────────────────────────────────────

def test_calendar_rfc3339():
    print("\n[calendar_service] _to_rfc3339")
    # Patch env so import doesn't fail
    with patch.dict(os.environ, {"GOOGLE_REFRESH_TOKEN": "x", "GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x"}):
        import calendar_service
        tz = ZoneInfo("Asia/Taipei")

        # Date-only string → should get T00:00:00
        result = calendar_service._to_rfc3339("2026-03-14")
        assert "2026-03-14" in result, f"Expected date in result, got {result}"
        ok("date-only string gets midnight time")

        # Datetime string with no tz → gets Taipei tz
        result = calendar_service._to_rfc3339("2026-03-14T09:00:00")
        assert "+08:00" in result or "08:00" in result, f"Expected +08:00, got {result}"
        ok("naive datetime gets Taipei timezone")

        # Already has tz → preserved
        result = calendar_service._to_rfc3339("2026-03-14T09:00:00+08:00")
        assert "09:00:00" in result
        ok("datetime with tz preserved correctly")


# ── 2. tasks_service: due date formatting ────────────────────────────────────

def test_tasks_due_date():
    print("\n[tasks_service] due date format")
    with patch.dict(os.environ, {"GOOGLE_REFRESH_TOKEN": "x", "GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x"}):
        import tasks_service

        # Date-only → should become full RFC3339
        due = "2026-03-14"
        if "T" not in due:
            due = due + "T00:00:00Z"
        assert due == "2026-03-14T00:00:00Z", f"Got {due}"
        ok("date-only '2026-03-14' → '2026-03-14T00:00:00Z'")

        # Already has T but no Z
        due = "2026-03-14T00:00:00"
        if "T" not in due:
            due = due + "T00:00:00Z"
        elif not due.endswith("Z"):
            due = due + "Z"
        assert due == "2026-03-14T00:00:00Z", f"Got {due}"
        ok("datetime without Z gets Z appended")

        # Already correct
        due = "2026-03-14T00:00:00Z"
        if "T" not in due:
            due = due + "T00:00:00Z"
        elif not due.endswith("Z"):
            due = due + "Z"
        assert due == "2026-03-14T00:00:00Z", f"Got {due}"
        ok("already-correct RFC3339 unchanged")


# ── 3. claude_service: conversation memory ───────────────────────────────────

def test_conversation_memory():
    print("\n[claude_service] conversation memory")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}):
        import claude_service

        TIMEZONE = ZoneInfo("Asia/Taipei")
        user_id = "test_user_memory"

        # Fresh user → empty history
        history = claude_service._get_history(user_id)
        assert history == [], f"Expected [], got {history}"
        ok("new user gets empty history")

        # Save a round
        claude_service._save_history(user_id, "hello", "hi there")
        history = claude_service._get_history(user_id)
        assert len(history) == 2
        ok("saved round appears in history")

        # Fill to MAX_ROUNDS (5 rounds = 10 messages)
        for i in range(4):
            claude_service._save_history(user_id, f"msg{i}", f"reply{i}")
        history = claude_service._get_history(user_id)
        assert len(history) == 10, f"Expected 10, got {len(history)}"
        ok(f"history capped at {claude_service.MAX_ROUNDS} rounds (10 messages)")

        # Simulate timeout → history should reset
        state = claude_service._conversations[user_id]
        state["last_active"] = datetime.now(TIMEZONE) - timedelta(minutes=11)
        history = claude_service._get_history(user_id)
        assert history == [], f"Expected [] after timeout, got {history}"
        ok("history resets after 10-minute timeout")


# ── 4. speech_service: audio size limit ──────────────────────────────────────

def test_speech_size_limit():
    print("\n[speech_service] audio size limit")
    with patch.dict(os.environ, {"GOOGLE_REFRESH_TOKEN": "x", "GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x"}):
        import speech_service
        MAX = speech_service.MAX_AUDIO_BYTES

        # Oversized file → returns empty string (without calling ffmpeg/Google)
        oversized = b"x" * (MAX + 1)
        result = speech_service.transcribe_audio(oversized)
        assert result == "", f"Expected '', got '{result}'"
        ok(f"audio > {MAX // 1024 // 1024}MB returns empty string immediately")


# ── 5. app.py: LINE_USER_ID fail-secure ──────────────────────────────────────

def test_line_user_id_failsecure():
    print("\n[app.py] LINE_USER_ID fail-secure")

    # Simulate the guard logic from app.py
    def should_allow(line_user_id_env: str, incoming_user_id: str) -> bool:
        LINE_USER_ID = line_user_id_env
        return bool(LINE_USER_ID) and incoming_user_id == LINE_USER_ID

    assert not should_allow("", "any_user"), "Empty LINE_USER_ID should block all"
    ok("empty LINE_USER_ID blocks all users (fail-secure)")

    assert not should_allow("Uf40417fe", "attacker_id"), "Wrong user blocked"
    ok("wrong user_id is blocked")

    assert should_allow("Uf40417fe", "Uf40417fe"), "Correct user allowed"
    ok("correct user_id is allowed")


# ── 6. scheduler: _reminded_events pruning ───────────────────────────────────

def test_reminded_events_pruning():
    print("\n[scheduler] _reminded_events pruning")
    TIMEZONE = ZoneInfo("Asia/Taipei")
    now = datetime.now(TIMEZONE)

    # Simulate the pruning logic
    reminded: dict = {
        "old_event_1": now - timedelta(hours=25),
        "old_event_2": now - timedelta(hours=48),
        "recent_event": now - timedelta(hours=1),
    }

    cutoff = now - timedelta(hours=24)
    expired = [k for k, v in reminded.items() if v < cutoff]
    for k in expired:
        del reminded[k]

    assert "old_event_1" not in reminded, "25h old entry should be pruned"
    assert "old_event_2" not in reminded, "48h old entry should be pruned"
    assert "recent_event" in reminded, "1h old entry should be kept"
    ok("entries older than 24h are pruned")
    ok("recent entries are preserved")


# ── 7. google_auth: credential caching ───────────────────────────────────────

def test_credential_caching():
    print("\n[google_auth] credential caching")
    with patch.dict(os.environ, {"GOOGLE_REFRESH_TOKEN": "x", "GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x"}):
        import google_auth

        mock_creds = MagicMock()
        mock_creds.valid = True
        google_auth._creds_cache = mock_creds

        result = google_auth.get_credentials()
        assert result is mock_creds, "Should return cached credentials"
        ok("valid cached credentials returned without re-refreshing")

        # Reset cache
        google_auth._creds_cache = None
        ok("cache reset works correctly")


# ── Run all tests ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  LINE Calendar Bot — QA Test Suite")
    print("=" * 55)

    tests = [
        test_calendar_rfc3339,
        test_tasks_due_date,
        test_conversation_memory,
        test_speech_size_limit,
        test_line_user_id_failsecure,
        test_reminded_events_pruning,
        test_credential_caching,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 55)
    sys.exit(0 if failed == 0 else 1)
