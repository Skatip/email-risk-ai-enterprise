# Enterprise Email AI – Final Intelligence Revision

This build preserves the existing UI/API wiring while fixing the issues discussed during live testing.

## Implemented
- Semantic Primary + Spam candidate ranking; newsletters/job feeds/bulk automation no longer win just because they are newest.
- Security and family/personal badges are driven by semantic backend fields only; no frontend keyword inference.
- Unified Communication Brain reads the current body, recent Gmail thread, reply style memory, and attachment intelligence before deciding DRAFT_REPLY / NO_REPLY / ASK_USER / ACTION_ONLY / DRAFT_AND_ACTION / WAIT / ESCALATE.
- Grounding prompt explicitly forbids invented availability, approvals, dates, amounts, attachments, promises, or completed actions.
- Conditional verification remains bounded to one verification call.
- Multi-document Gmail attachment analysis: every attachment can be parsed/OCR'd, cached by SHA-256 in PostgreSQL, and combined into one cross-document intelligence bundle.
- Reply generation automatically analyzes all attachments when needed, so replies are grounded in all documents, not only one file.
- Thread-aware reply generation fetches the full Gmail thread automatically.
- User-approved `Save to Gmail thread` creates a Gmail draft with the original threadId plus In-Reply-To / References headers. It does not auto-send.
- Google OAuth now requests gmail.compose in addition to gmail.readonly. Existing users must reconnect once to grant compose permission.
- Follow-ups/reminders are user-scoped in PostgreSQL and can use the Communication Brain's follow-up recommendation instead of keyword detection.
- Inbox cache and attachment intelligence are scoped by user.
- Frontend restores the connected Gmail workspace after OAuth.

## Important testing note
After replacing this code, reconnect Gmail once because the OAuth scope set now includes `https://www.googleapis.com/auth/gmail.compose` for same-thread draft creation.
