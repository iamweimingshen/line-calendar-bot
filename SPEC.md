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
Render.com (Free tier)
  └─ FastAPI server (app.py)
        │
        ├─ Text message ──────────────────────────────────┐
        │                                                  │
        └─ Voice message                                   │
              │                                            │
              ▼                                            │
        Google Speech-to-Text API                         │
        (m4a → FLAC → transcript)                         │
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
```

---

## Components

| Component | Tech | Role |
|---|---|---|
| Bot interface | LINE Messaging API | Receive/send messages |
| Web server | FastAPI + uvicorn | Handle webhooks |
| Hosting | Render.com (Free) | 24/7 public HTTPS endpoint |
| AI brain | Claude Sonnet 4.6 | NLP + tool use |
| Voice STT | Google Speech-to-Text | m4a → text |
| Calendar | Google Calendar API v3 | CRUD events |
| Auth | Google OAuth2 refresh token | Persistent access |

---

## Message Flow

### Text message
1. User sends text in LINE
2. LINE sends POST to `/webhook`
3. Signature verified (LINE_CHANNEL_SECRET)
4. User ID checked (only Brian can use it)
5. Text passed to Claude with tool definitions
6. Claude calls tools (create/get/update/delete event)
7. Tools execute against Google Calendar
8. Claude returns friendly reply
9. Bot replies via LINE reply token

### Voice message
1-4. Same as above
5. Audio downloaded from LINE blob API
6. Saved as temp m4a file
7. ffmpeg converts m4a → FLAC (16kHz mono)
8. Google STT transcribes FLAC → text
9. Text passed to Claude (same as step 5 above)
10. Continue same as text flow

---

## Security

- Webhook signature verification (HMAC-SHA256)
- User ID whitelist (only responds to Brian's LINE ID)
- All secrets in environment variables (never in code)
- Google OAuth limited to Calendar + Cloud Platform scopes
- Google Cloud project in Testing mode (no public access)

---

## Cost Estimate

### Monthly (personal use, ~50 interactions/day)

| Service | Free tier | Est. usage | Est. cost |
|---|---|---|---|
| **Render** | 750 hrs/month | ~720 hrs | **$0** |
| **LINE Messaging API** | 500 msgs/month free | ~50/day = 1,500/mo | **~$0** (200 msgs = $3, but personal bots usually exempt) |
| **Anthropic Claude Sonnet 4.6** | None | ~50 msgs × ~500 tokens = 25K tokens/day → 750K/month | **~$3–5/month** |
| **Google Calendar API** | Free | Unlimited for personal | **$0** |
| **Google Speech-to-Text** | 60 min/month free | ~10 voice msgs/day × 5s = ~25 min/month | **$0** |
| **Total** | | | **~$3–5/month** |

### Cost drivers
- Main cost is **Claude API** (input + output tokens)
- If you use more voice: STT is $0.006/min after 60 min free → negligible
- LINE free tier: 200 reply messages/month on free plan, upgrade to $3/month for more

### To reduce costs
- Cache frequent queries (e.g. "what's today's schedule")
- Use Claude Haiku ($0.25/MTok) instead of Sonnet for simple queries

---

## Limitations (current)

- No conversation memory (each message is stateless)
- Free Render instance sleeps after 15 min inactivity → first reply takes ~50 sec
- Voice only supports m4a (LINE default); no other formats
- Max 5000 characters per LINE message reply
- Google refresh token expires if unused for 6 months

---

## Potential Improvements

- [ ] Add conversation history (Redis or in-memory)
- [ ] Upgrade Render to Starter ($7/month) for always-on
- [ ] Push notifications (remind before events)
- [ ] Image/sticker support
- [ ] Multi-calendar support
