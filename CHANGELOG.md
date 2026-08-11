## 2026-08-10 – Final semantic communication build
- Added multi-document OCR/intelligence aggregation and SHA-256 PostgreSQL cache.
- Added grounded full-thread reply context and same-thread Gmail draft creation.
- Added gmail.compose OAuth scope for user-approved draft actions.
- Made reminders/follow-ups tenant scoped and Communication-Brain driven.
- Preserved semantic security/personal classification; removed keyword badge behavior.

# Changelog

## v0.7.0 Preview

- Added AI Document Intelligence Engine
- Added OCR support
- Added attachment classification
- Improved thread summary
- Improved follow-up/reminder workflow
- Added async backend foundation
- Added speed-first architecture direction

## Earlier Versions

- Initial AI email platform
- Gmail integration
- Reply generation
- Priority scoring
- Basic analytics

## Enterprise Semantic Inbox + Communication Brain Revision
- Replaced Gmail-order inbox display with one bounded semantic triage call over a larger Primary + Spam candidate pool.
- Direct human, action-required, genuine security, family/personal, work, deadline, and document messages are ranked above bulk feeds/newsletters/promotions.
- Removed frontend keyword-based Security and Family/Personal inference; UI now displays semantic backend decisions only.
- Removed Gmail-domain-based semantic classification from Gmail transport layer.
- Deep per-email analysis now uses OpenAI semantic understanding instead of the legacy priority keyword pipeline.
- Reply generation now automatically fetches the full Gmail body and recent thread when user context is available.
- Communication Brain strengthened to ask the user instead of inventing missing decisions/facts.
- Multi Reply reduced from three model calls to one grounded call.
- User-specific inbox and attachment cache keys added.
- Approved reply examples now retain user_id and are loaded as compact reply-style memory.
- Frontend passes user_id to reply, thread summary, analysis, and attachment operations.
