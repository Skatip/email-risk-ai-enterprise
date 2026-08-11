# Fast Inbox — Uvicorn-only production patch

This build is optimized for the actual deployment: Vercel frontend + Render FastAPI/Uvicorn + existing PostgreSQL/Neon + Gmail OAuth. It does not require Redis, Celery, or a Render background worker.

## Load path
1. Gmail Primary + Spam IDs are listed for the bounded 7-day window.
2. Message metadata is fetched using Gmail HTTP batching instead of one network round-trip per email.
3. Previously analyzed semantic intelligence is read from PostgreSQL immediately.
4. Only new/stale messages are submitted to a bounded in-process ThreadPoolExecutor.
5. `/inbox` returns immediately with available cards; the frontend quietly polls while pending cards are enriched.
6. Completed semantic results are persisted and reused on refresh/redeploy.
7. Switching UI buckets is local and does not re-fetch Gmail or re-run the LLM.

## Render environment
Recommended additions:

```env
AI_ASYNC_ENABLED=false
INBOX_CACHE_TTL_SECONDS=30
RAW_INBOX_CACHE_TTL_SECONDS=30
INBOX_SEMANTIC_CACHE_TTL_SECONDS=604800
INBOX_BACKGROUND_WORKERS=2
```

Keep all existing DATABASE_URL, Google OAuth, AI provider, CORS and deployment variables unchanged.

## Preserved behavior
- Communication Brain semantic triage
- Primary + Spam recovery
- reply/no-reply logic
- full body/thread deep analysis on demand
- attachment OCR/document intelligence with cache
- reply, multi-reply, summaries, follow-ups
- OAuth/MCP wiring
- dark/light theme, typography and importance styling
- optimized enterprise inbox buckets; attachments remain part of their emails
