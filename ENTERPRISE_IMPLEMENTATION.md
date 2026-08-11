# Enterprise Email AI implementation

The existing inbox, Primary + Spam recovery, attachment UI, thread summaries, follow-ups, family/security highlights, and API contracts are preserved.

## Implemented layers

1. **Hosted OpenAI provider** — no local model installation or fallback.
2. **Unified Communication Brain** — understands complete message meaning and returns draft, no-reply, ask-user, action, follow-up, commitment, confidence, and explanation in one structured decision.
3. **Compact context builder** — limits current body, recent thread messages, memories, preferences, and attachment summaries.
4. **Bounded verification** — second model call only for low-confidence or consequential results.
5. **One-click Google OAuth** — application-owned credentials and encrypted user refresh tokens.
6. **Neon PostgreSQL foundation** — persistent users, integration connections, summaries, memory, reminders, analytics, usage, and audit records.
7. **Minimal MCP-compatible tools** — Gmail read/search/thread operations now; Calendar, Slack, Jira, and approved writes can be registered later.
8. **Supabase private storage adapter** — optional attachment persistence with content-hash paths.
9. **Hosted deployment files** — Render backend and Vercel frontend configuration.
10. **Strict resource design** — maximum context, output, tool rounds, verification calls, and revisions.

## Final flow

User → Google consent → incremental Gmail retrieval → inbox/spam/attachment ingestion → compact context → rolling memory and attachment intelligence → Communication Brain → conditional routing and verification → draft/no-reply/ask-user/follow-up/action → user approval → Gmail/Calendar/MCP action → feedback memory.
