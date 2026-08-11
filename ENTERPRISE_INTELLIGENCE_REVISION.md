# Enterprise Intelligence Revision

This build keeps the current UI/API wiring while correcting the intelligence path.

## Intelligent Inbox
- Gmail Primary + Spam are retrieval sources, not final ranking rules.
- A bounded candidate pool is semantically triaged in one OpenAI call.
- Direct human, action-required, genuine security, family/personal, important work/school/client, deadline, and document messages rank above feeds/newsletters/promotions.
- One thread is represented once in the candidate set.
- Cache keys include user_id.

## Communication Brain / Replies
- Full Gmail body is fetched before reply generation when needed.
- Recent thread messages are fetched automatically when available.
- Attachment intelligence is passed into the same brain.
- Approved user replies are loaded as compact style memory.
- The brain returns DRAFT_REPLY, NO_REPLY, ASK_USER, ACTION_ONLY, DRAFT_AND_ACTION, WAIT, or ESCALATE.
- Missing decisions/facts cause ASK_USER rather than hallucination.
- Verification is conditional and bounded to one extra call.
- Multi Reply uses one grounded model call instead of three independent calls.

## Frontend Semantics
- Security highlighting uses `security_event === true` from semantic AI output.
- Family/personal highlighting uses semantic relationship output.
- React no longer infers security from words such as "security", "login", or "verification".
- React no longer infers family/personal merely from consumer email domains.
