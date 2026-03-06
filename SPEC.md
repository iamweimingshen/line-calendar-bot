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
                                              - Understands intent
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
| AI brain | Claude Sonnet 4.6 | NLP + tool use |
| Voice STT | Google Speech-to-Text | m4a → FLAC via ffmpeg subprocess |
| Calendar | Google Calendar API v3 | CRUD events |
| Scheduler | APScheduler (AsyncIOScheduler) | Background jobs |
| Auth | Google OAuth2 refresh token | Persistent access |

---

## Features

### On-demand (user-triggered)
| Feature | Example |
|---|---|
| Create event | 「明天下午三點開會」|
| Query events | 「這週有什麼行程？」|
| Update event | 「把週五開會改到六點」|
| Delete event | 「刪掉明天的牙醫」|
| Voice input | 直接傳語音訊息 |

### Proactive (scheduler-triggered)
| Feature | Time | Detail |
|---|---|---|
| 早安通知 | 每天 07:00 | 今天 + 明天完整行程（整天 + 有時間的） |
| 15 分鐘提醒 | 開始前 15 分鐘 | 僅限有時間的行程，整天行程不提醒 |
| Self-ping | 每 5 分鐘 | 防止 Render 免費方案 sleep |

---

## Message Flow

### Text message
1. User sends text in LINE
2. LINE sends POST to `/webhook`
3. Signature verified (LINE_CHANNEL_SECRET)
4. User ID checked (only Brian)
5. Text passed to Claude with tool definitions
6. Claude calls tools (create/get/update/delete)
7. Tools execute against Google Calendar
8. Claude returns friendly reply
9. Bot replies via LINE reply token

### Voice message
1–4. Same as above
5. Audio downloaded from LINE blob API
6. ffmpeg converts m4a → FLAC (16kHz mono)
7. Google STT transcribes FLAC → text
8. Text passed to Claude (same as step 5)
9. Continue same as text flow

### Morning briefing (7am)
1. Scheduler fires at 07:00 Taipei time
2. Fetch events: today 00:00 ~ tomorrow 23:59
3. Format list (all-day events shown as「整天」)
4. Push to LINE via push message API

### 15-min reminder
1. Scheduler checks every minute
2. Query events in 1-min window around (now + 15 min)
3. Skip all-day events (no `dateTime` in start)
4. Skip already-reminded events (in-memory dedup set)
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

### Assumptions (personal use)
- 30 interactions/day via text or voice
- ~10 voice messages/day × 10 seconds each
- App runs 24/7 (self-ping keeps it alive)

### Monthly breakdown

| Service | Free tier | Est. usage | Est. cost |
|---|---|---|---|
| **Render** | 750 hrs/month | 720 hrs | **$0** |
| **Claude Sonnet 4.6** | None | 30 msgs/day × ~600 tokens avg × 30 days = ~540K tokens/month | **~$2–4/month** |
| **Google Calendar API** | Free | Unlimited personal use | **$0** |
| **Google Speech-to-Text** | 60 min/month free | 10 msgs/day × 10s = ~50 min/month | **$0** |
| **LINE Messaging API** | 200 push msgs/month free | ~60 push/month (30 briefings + 30 reminders) + reply msgs | **$0–3/month** |
| **Total** | | | **~$2–7/month** |

### Cost breakdown detail

**Claude API** (main cost):
- Input: system prompt (~200 tokens) + user message (~50 tokens) + tool results (~100 tokens) = ~350 tokens/msg
- Output: ~250 tokens/msg
- 30 msgs/day × 600 tokens × 30 days = 540K tokens/month
- Sonnet 4.6 pricing: $3/MTok input + $15/MTok output
- Est: ~$1.05 input + $1.35 output = **~$2.4/month**

**LINE push messages**:
- Free tier: 200 push messages/month
- Usage: 30 days × 1 briefing + ~30 reminders/month = ~60 push msgs
- Well within free tier → **$0**
- If usage grows: $3/month for 1,000 msgs

**Voice (Google STT)**:
- 10 voice msgs/day × 10s = ~50 min/month < 60 min free tier → **$0**

### To reduce costs further
- Switch to **Claude Haiku** ($0.25/MTok input, $1.25/MTok output) → ~$0.2/month
- Tradeoff: slightly less natural responses

---

## Limitations

- No conversation memory (each message is stateless)
- `_reminded_event_ids` resets on app restart (may re-remind after redeploy)
- Voice supports m4a only (LINE default format)
- Max 5000 characters per LINE message
- Google refresh token expires after 6 months of inactivity

---

## Potential Improvements

- [ ] Conversation memory (keep last N messages per session)
- [ ] Upgrade Render to Starter ($7/month) for guaranteed uptime
- [ ] Weekly summary (Sunday evening)
- [ ] Multi-calendar support
- [ ] Smart model routing (Haiku for simple queries, Sonnet for complex)
