# LINE Calendar Bot — System Spec

## Overview
A personal AI assistant on LINE that manages Google Calendar and Google Tasks via natural language (text and voice).

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
                                              - Auto-routes to Calendar or Tasks
                                              - Asks before acting on ambiguous input
                                              - Confirms before delete/update
                                                           │
                                      ┌────────────────────┴────────────────────┐
                                      │                                          │
                              Google Calendar API                      Google Tasks API
                              (time-based events)                      (todo items)
                              create / get / update / delete           create / get / complete / delete
```

**Background Scheduler (APScheduler — runs inside Render)**
```
  ├─ Every 5 min  → self-ping (keep Render awake)
  ├─ Every day 7am → morning briefing push (today + tomorrow calendar events)
  └─ Every 1 min  → 15-min reminder push (timed calendar events only)
```

---

## Components

| Component | Tech | Role |
|---|---|---|
| Bot interface | LINE Messaging API | Receive/send messages |
| Web server | FastAPI + uvicorn | Handle webhooks |
| Hosting | Render.com (Free) | 24/7 server — your Mac does NOT need to be on |
| AI brain | Claude Sonnet 4.6 | NLP + tool use + conversation memory |
| Voice STT | Google Speech-to-Text | m4a → FLAC via ffmpeg subprocess |
| Calendar | Google Calendar API v3 | Time-based event management |
| Tasks | Google Tasks API v1 | Todo item management |
| Scheduler | APScheduler | Background jobs (runs on Render) |
| Auth | Google OAuth2 refresh token | Single token covers all Google APIs |

---

## Features

### On-demand (user-triggered)
| Feature | Example | Backend |
|---|---|---|
| Create event | 「明天下午三點開會」 | Google Calendar |
| Query events | 「這週有什麼行程？」 | Google Calendar |
| Update event | 「把週五開會改到六點」 | Google Calendar |
| Delete event | 「刪掉明天的牙醫」 | Google Calendar |
| Create task | 「記得買牛奶」 | Google Tasks |
| List tasks | 「我有哪些待辦？」 | Google Tasks |
| Complete task | 「完成買牛奶」 | Google Tasks |
| Delete task | 「刪掉買牛奶這個任務」 | Google Tasks |
| Voice input | 傳語音訊息 | Google STT → Claude |
| Conversation memory | 追問、確認、多輪對話 | In-memory (10 min) |

**Auto-routing:** Claude automatically decides whether to use Calendar or Tasks based on context — no need to specify.

### Proactive (scheduler-triggered, no user action needed)
| Feature | Time | Detail |
|---|---|---|
| 早安通知 | 每天 07:00 | 今天 + 明天完整 Calendar 行程 |
| 15 分鐘提醒 | 開始前 15 分鐘 | 僅限有時間的 Calendar 行程，整天行程不提醒 |
| Self-ping | 每 5 分鐘 | 防止 Render 休眠（無需 UptimeRobot） |

### Safety rules
- 日期或時間不明確 → 追問，不自動猜測
- 刪除/修改前 → 列出找到的項目確認
- 多個項目符合 → 列出請用戶選擇
- 一問一答：每次最多問一個問題

---

## Message Flow

### Text message
1. User sends text in LINE
2. LINE sends POST to `/webhook`
3. Signature verified (HMAC-SHA256)
4. User ID checked (only Brian)
5. Load conversation history (if < 10 min since last message)
6. Text + history passed to Claude with all tool definitions
7. Claude auto-routes: Calendar or Tasks, asks if unclear
8. Tools execute against Google APIs
9. Claude returns friendly reply
10. Reply saved to conversation history
11. Bot replies via LINE reply token

### Voice message
1–4. Same as text flow
5. Audio downloaded from LINE blob API
6. ffmpeg converts m4a → FLAC (16kHz mono)
7. Google STT transcribes → text
8. Continue same as text flow from step 5

### Morning briefing (7am)
1. APScheduler fires at 07:00 Taipei time (on Render)
2. Fetch Calendar events: today 00:00 ~ tomorrow 23:59
3. All-day events shown as「整天」
4. Push message to LINE

### 15-min reminder
1. APScheduler checks every minute (on Render)
2. Query Calendar events in 1-min window around (now + 15 min)
3. Skip all-day events (no `dateTime` in start)
4. Skip already-reminded events (in-memory dedup set)
5. Push reminder to LINE

---

## Security

- Webhook signature verification (HMAC-SHA256)
- User ID whitelist (only Brian's LINE_USER_ID responds)
- All secrets in environment variables (never in code or GitHub)
- Google OAuth scopes: Calendar + Tasks + Cloud Platform only
- Google Cloud project in Testing mode (no public access)

---

## Cost Estimate

### Assumptions
- 30 interactions/day (text + voice combined)
- ~10 voice messages/day × 10 seconds each
- Average conversation: 2 rounds within a session (1 msg + 1 follow-up)
- App runs 24/7 via self-ping

### Token calculation per message

| Component | Tokens |
|---|---|
| System prompt | ~300 (slightly larger with Tasks rules) |
| Conversation history (avg 1 prior round) | ~300 |
| User message | ~50 |
| Tool results | ~150 (more tools = slightly larger results) |
| **Total input per message** | **~800** |
| Claude reply (output) | ~250 |

### Monthly breakdown

| Service | Free tier | Est. usage | Est. cost |
|---|---|---|---|
| **Render** | 750 hrs/month | 720 hrs | **$0** |
| **Claude Sonnet 4.6 — input** | None | 30 msgs/day × 800 tokens × 30 days = 720K tokens × $3/MTok | **$2.16** |
| **Claude Sonnet 4.6 — output** | None | 30 msgs/day × 250 tokens × 30 days = 225K tokens × $15/MTok | **$3.38** |
| **Google Calendar API** | Free | Unlimited personal | **$0** |
| **Google Tasks API** | Free | Unlimited personal | **$0** |
| **Google Speech-to-Text** | 60 min/month free | 10 msgs × 10s × 30 days = 50 min | **$0** |
| **LINE Messaging API** | 200 push/month free | ~60 push msgs (briefings + reminders) | **$0** |
| **Total** | | | **~$5.5/month** |

### Cost sensitivity

| Usage level | Msgs/day | Est. monthly |
|---|---|---|
| Light | 15 | ~$2.8 |
| Normal (current assumption) | 30 | ~$5.5 |
| Heavy | 50 | ~$9.0 |

### Key notes
- **Output tokens are 5× more expensive** than input ($15 vs $3/MTok) — Claude's reply length drives cost more than message history
- Google Tasks API is completely free — zero added cost vs Calendar-only
- Voice adds no cost within the 60 min/month free tier
- Switching to **Claude Haiku** would cost ~$0.5/month but with lower response quality

---

## Limitations

- Conversation memory resets on app restart/redeploy (in-memory only)
- `_reminded_event_ids` resets on restart (may re-remind after redeploy)
- Morning briefing covers Calendar only — Tasks not included
- Voice supports m4a only (LINE default format)
- Max 5000 characters per LINE message
- Google refresh token expires after 6 months of inactivity

---

## Potential Improvements

- [ ] Include Tasks summary in morning briefing
- [ ] Weekly summary (Sunday evening)
- [ ] Task due date reminders
- [ ] Smart model routing (Haiku for simple queries, Sonnet for complex)
- [ ] Upgrade Render to Starter ($7/month) for guaranteed uptime + persistent memory
