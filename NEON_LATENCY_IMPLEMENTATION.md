# Neon-backed inbox latency implementation

## Goal
Keep the existing Email-AI behavior and Communication Brain, while removing repeated Gmail metadata fetches and repeated LLM triage every time the app opens.

## New request path
1. Gmail OAuth remains the source of authorization.
2. `/inbox` performs lightweight Gmail `messages.list` calls to discover the current message IDs in the existing 7-day Primary + Spam scope.
3. Email-AI looks those IDs up in Neon (`inbox_messages`).
4. Existing messages reuse persisted metadata and semantic triage.
5. Only new Gmail IDs are fetched. Their metadata is fetched through Gmail HTTP batch requests instead of one sequential request per message.
6. Only new/stale-version messages are sent to the Communication Brain.
7. New metadata and semantic results are persisted in Neon and returned through the existing API shape.

This preserves the existing UI wiring and does not progressively show partially analyzed cards.

## Neon table
`inbox_messages` is created automatically during backend startup. It is scoped by `(user_id, provider, email_id)` and stores metadata JSON, semantic JSON, message/thread IDs, timestamps, and `analysis_version`.

`analysis_version` allows a future Communication Brain change to invalidate semantic results without refetching Gmail metadata.

## Environment
No new secret is required. The implementation uses the existing `DATABASE_URL`. Optional:

`INBOX_ANALYSIS_VERSION=semantic-v2`

Change this value only when the semantic contract changes and all current messages should be re-triaged.

## Expected behavior
- First OAuth/sync: still performs Gmail discovery, metadata fetch, and semantic analysis. It is faster than before because metadata GETs are batched.
- Later launches: Gmail discovery + Neon reads; previously analyzed messages do not incur per-message Gmail metadata GETs or repeated LLM triage.
- New mail: only new IDs receive metadata fetch + triage.
- RAG/pgvector is intentionally not added in this change. This persistence layer is the foundation for that next phase.
