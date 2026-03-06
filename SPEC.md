# LINE Calendar Bot — System Spec

## Overview
A personal AI assistant on LINE that manages Google Calendar via natural language (text and voice).

---

## Architecture

```
User (LINE app)
    │
    │ HTTPS webhook
    ▼
Render.com (Free tier, Python 3.11)
  └─ FastAPI server (app.py)
        │
        ├─ Text message ──────────────────────────────────┐
        │                                                  │
        └─ Voice message                                   │
              │                                            │
              ▼                                            │
        Google Speech-to-Text API                         │
        (m4a → ffmpeg → FLAC → transcript)                │
              │                                            │
              └──────────────────────────────────────────▶│
                                                           ▼
                                              Claude Sonnet 4.6 (Anthropic)
                                              - Conversation memory (5 rounds, 10-min timeout)
                                              - Asks before acting on ambiguous input
                                              - Confirms before delete/update
                                              - Calls calendar tools
                                                           │
                                              ┌────────────┼────────────┐
                                              ▼            ▼            ▼
                                         create_event  get_events  delete/update
                                              └────────────┼────────────┘
                                                           ▼
                                              Google Calendar API
                                              (primary calendar)
                                                           │
                                                           ▼
                                              Reply back to LINE user

Background Scheduler (APScheduler)
  ├─ Every 5 min  → self-ping (keep Render awake)
  ├─ Every day 7am → morning briefing push (today + tomorrow)
  └─ Every 1 min  → 15-min reminder push (timed events only)
```

---

## Components

| Component | Tech | Role |
|---|---|---|
| Bot interface | LINE Messaging API | Receive/send messages |
| Web server | FastAPI + uvicorn | Handle webhooks |
| Hosting | Render.com (Free) | 24/7 public HTTPS endpoint |
| AI brain | Claude Sonnet 4.6 | NLP + tool use + conversation memory |
| Voice STT | Google Speech-to-Text | m4a → FLAC via ffmpeg subprocess |
| Calendar | Google Calendar API v3 | CRUD events |
| Scheduler | APScheduler (AsyncIOScheduler) | Background jobs |
| Auth | Google OAuth2 refresh token | Persistent access |

---

## Features

### On-demand (user-triggered)
| Feature | Detail |
|---|---|
| Create event | 問缺少的日期或時間才建立 |
| Query events | 查詢任意時間範圍的行程 |
| Update event | 先確認找到的行程再修改 |
| Delete event | 先確認找到的行程再刪除 |
| Voice input | 語音自動轉文字後處理 |
| Conversation memory | 10 分鐘內保留最多 5 輪對話 |

### Proactive (scheduler-triggered)
| Feature | Time | Detail |
|---|---|---|
| 早安通知 | 每天 07:00 | 今天 + 明天完整行程 |
| 15 分鐘提醒 | 開始前 15 分鐘 | 僅限有時間的行程，整天行程不提醒 |
| Self-ping | 每 5 分鐘 | 防止 Render 免費方案 sleep |

### Safety rules
- 日期或時間不明確 → 追問，不自動猜測
- 刪除/修改前 → 列出找到的行程確認
- 多個行程符合 → 列出請用戶選擇

---

## Message Flow

### Text message
1. User sends text in LINE
2. LINE sends POST to `/webhook`
3. Signature verified (LINE_CHANNEL_SECRET)
4. User ID checked (only Brian)
5. Load conversation history (if < 10 min since last message)
6. Text + history passed to Claude with tool definitions
7. Claude asks if unclear, or calls tools directly
8. Tools execute against Google Calendar
9. Claude returns friendly reply
10. Reply saved to conversation history
11. Bot replies via LINE reply token

### Voice message
1–4. Same as above
5. Audio downloaded from LINE blob API
6. ffmpeg converts m4a → FLAC (16kHz mono)
7. Google STT transcribes FLAC → text
8. Continue same as text flow from step 5

### Morning briefing (7am)
1. Scheduler fires at 07:00 Taipei time
2. Fetch events: today 00:00 ~ tomorrow 23:59
3. All-day events shown as「整天」
4. Push to LINE

### 15-min reminder
1. Scheduler checks every minute
2. Query events in 1-min window around (now + 15 min)
3. Skip all-day events
4. Skip already-reminded events (in-memory dedup)
5. Push reminder to LINE

---

## Security

- Webhook signature verification (HMAC-SHA256)
- User ID whitelist (only Brian's LINE_USER_ID)
- All secrets in environment variables (never in code)
- Google OAuth scopes: Calendar + Cloud Platform only
- Google Cloud project in Testing mode (no public access)

---

## Cost Estimate

### Assumptions
- 30 interactions/day (text + voice combined)
- ~10 voice messages/day × 10 seconds each
- Average conversation: 2 rounds (1 user message + 1 follow-up in same session)
- App runs 24/7 via self-ping

### Token calculation per message

| Component | Tokens |
|---|---|
| System prompt | ~250 |
| Conversation history (avg 1 prior round) | ~300 |
| User message | ~50 |
| Tool results | ~100 |
| **Total input per message** | **~700** |
| Claude reply (output) | ~250 |

### Monthly breakdown

| Service | Free tier | Est. usage | Est. cost |
|---|---|---|---|
| **Render** | 750 hrs/month | 720 hrs | **$0** |
| **Claude Sonnet 4.6 — input** | None | 30 msgs/day × 700 tokens × 30 days = 630K tokens | **$1.89** |
| **Claude Sonnet 4.6 — output** | None | 30 msgs/day × 250 tokens × 30 days = 225K tokens | **$3.38** |
| **Google Calendar API** | Free | Unlimited personal | **$0** |
| **Google Speech-to-Text** | 60 min/month free | 10 msgs × 10s × 30 days = 50 min | **$0** |
| **LINE Messaging API** | 200 push/month free | ~60 push msgs (briefings + reminders) | **$0** |
| **Total** | | | **~$5.3/month** |

### Notes
- Output tokens ($15/MTok) are the main cost driver, not input ($3/MTok)
- If you use the bot more heavily (50 msgs/day): ~$8–9/month
- If you switch to **Claude Haiku**: ~$0.5/month but lower quality

### Cost vs no-memory version
| | No memory | With memory (current) |
|---|---|---|
| Input tokens/msg | ~350 | ~700 (+100%) |
| Output tokens/msg | ~250 | ~250 (same) |
| Monthly total | ~$2.4 | ~$5.3 |
| Difference | — | +$2.9/month |

The extra $2.9/month buys: follow-up questions that actually work, safer delete/update confirmations.

---

## Limitations

- Conversation memory is in-memory — resets on app restart/redeploy
- `_reminded_event_ids` resets on restart (may re-remind after redeploy)
- Voice supports m4a only (LINE default format)
- Max 5000 characters per LINE message
- Google refresh token expires after 6 months of inactivity

---

## Potential Improvements

- [ ] Weekly summary (Sunday evening)
- [ ] Multi-calendar support
- [ ] Smart model routing (Haiku for simple queries, Sonnet for complex)
- [ ] Upgrade Render to Starter ($7/month) for guaranteed uptime + persistent memory
