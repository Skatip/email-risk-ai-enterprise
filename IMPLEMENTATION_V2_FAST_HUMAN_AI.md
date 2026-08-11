# Fast Human-Centered Email AI — implementation

## What changed
- Default inbox is curated `IMPORTANT`, not All Mail.
- Semantic buckets: IMPORTANT_NOW, CONVERSATIONAL, BUSINESS, RECRUITING, SECURITY, FOLLOW_UP, TRANSACTIONAL, INFORMATIONAL, JOB_FEED, MARKETING, SOCIAL, AUTOMATED_LOW_VALUE, SPAM.
- Initial load uses metadata/snippets only; no full-body analysis and no OCR before rendering.
- Compact triage batches run concurrently with bounded concurrency.
- Full body + thread + all meaningful attachments are analyzed lazily when the user opens an email or requests a reply.
- OCR/native extraction is cleaned and then sent through OpenAI Document Intelligence; replies consume structured document facts rather than raw OCR.
- Communication Brain is the source of truth for reply/no-reply/ask-user/actions/follow-ups.
- Scheduling can request a read-only Google Calendar free/busy lookup; availability is never invented and no event is auto-created.
- Existing Gmail thread reply-draft wiring remains intact.

## Google OAuth change
Calendar availability requires `https://www.googleapis.com/auth/calendar.readonly`. Existing users must reconnect Google once after deployment to grant this scope.
