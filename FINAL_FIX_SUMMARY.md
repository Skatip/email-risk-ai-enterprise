# Email AI — consolidated intelligence fix

This build removes the duplicate/legacy intelligence stack and makes the hosted OpenAI Communication Brain the semantic source of truth.

## Fixed in this revision

- Semantic inbox triage now runs in bounded batches with strict structured output instead of one oversized JSON completion. A truncated batch is split and retried; the entire inbox no longer falls back to newest-first because one model response was cut off.
- Gmail HTML-only messages are converted to readable body text. The AI no longer receives only a snippet for common recruiting, university, banking, and notification emails.
- Provider-generated HTML body artifacts such as `this_message_in_html.html` are excluded from attachment intelligence.
- Deep email analysis now reads the full Gmail body, recent full thread, and all attachment intelligence together.
- Multiple real attachments are fetched, SHA-256 cached, analyzed, and aggregated into one cross-document context.
- Native PDF/DOCX/XLSX/text extraction remains first. Scanned PDFs/images use local Tesseract when available and a bounded OpenAI vision OCR fallback when hosted Render cannot provide usable OCR text.
- The Communication Brain has a strict structured schema and explicit NO_REPLY vs ASK_USER behavior. Automated rejection/status/receipt messages no longer ask the user a clarification question merely to offer assistance.
- Same-thread Gmail drafts remain approval-only and preserve `threadId`, `In-Reply-To`, and `References`.
- Security is semantic only; company names/job titles containing “security” cannot trigger a security badge by themselves.
- Follow-up/reminder and commitment output remains part of the Communication Brain and is stored per user.
- Analytics queries are now user-scoped.
- Outlook app-password behavior is disabled. The UI marks Outlook OAuth as coming next instead of asking nontechnical users for app passwords.

## Removed as unused/legacy

The old parallel keyword/score pipeline and unused worker scaffolding were removed, including the legacy priority/risk/intent/sender-rule modules, Celery bridge files, obsolete RAG helper files, unused React screens, and duplicate dependency files.

## Production flow

Gmail OAuth → bounded Primary+Spam candidate pool → semantic triage batches → intelligent ranking → full-body/thread/document deep analysis → Communication Brain → NO_REPLY / DRAFT_REPLY / ASK_USER / ACTION / FOLLOW-UP → user approval → same-thread Gmail draft.

## Important environment additions

- `OPENAI_VISION_MODEL`
- `INBOX_TRIAGE_BATCH_SIZE`
- `INBOX_TRIAGE_BATCH_MAX_TOKENS`
- `ENABLE_VISION_OCR_FALLBACK`
- `VISION_OCR_MAX_TOKENS`

Use the values in `backend/.env.example` as the reference.
