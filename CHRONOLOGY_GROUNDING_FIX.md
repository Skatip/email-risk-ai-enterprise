# Communication chronology + grounding patch

This patch preserves the restored inbox behavior and only fixes communication correctness/UX:

- Scheduling replies now follow: read calendar -> ask the user -> draft after explicit user confirmation.
- A free calendar is never treated as proof that the user is available.
- Reply grounding explicitly blocks invented meeting agenda/details.
- Deep analysis can create a grounded follow-up reminder for concrete future obligations.
- Gmail attachment metadata returned during deep/reply analysis is patched back into the email card.
- Attachment actions are labeled Summarize / Summarize all for clarity.
- Internal `used_rag: undefined` metadata is no longer exposed.

No Redis/Celery/progressive inbox-loading changes are introduced.
