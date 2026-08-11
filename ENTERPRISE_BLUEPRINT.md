# Enterprise Communication Intelligence Build

This build preserves the existing inbox, smart spam recovery, attachment intelligence, follow-ups, analytics, and frontend/API contracts while adding:

- OpenAI-only hosted AI provider for production and testing.
- One semantic Communication Brain for reply, no-reply, clarification, action and commitment decisions.
- Compact contextual retrieval with strict context limits.
- Conditional bounded verification with at most one verification pass.
- One-click Google OAuth endpoints and encrypted connection storage.
- Minimal MCP-compatible Gmail and Calendar tool registry.
- Existing attachment intelligence reusable as cached reply context.

## Production follow-ups before public launch

- Move integration credentials from the included local encrypted store to managed PostgreSQL.
- Derive `user_id` from a verified session/JWT rather than browser input.
- Add Calendar OAuth scope only when scheduling is enabled.
- Complete Google OAuth verification before broad public Gmail access.
- Persist rolling summaries, structured memory, attachment hashes, AI usage, and audit logs in PostgreSQL.
