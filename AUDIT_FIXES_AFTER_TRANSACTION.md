# Post-transaction audit fixes

This pass reviewed the Neon persistence and Ask Email-AI additions after the PostgreSQL transaction fix.

Additional fixes:
- RAG version bumped to `email-rag-v2` so documents created with failed/empty embeddings are rebuilt.
- Failed embedding batches are no longer stored as successfully indexed documents; a later sync retries them.
- Retrieval scans up to 5,000 indexed messages by default (configurable with `EMAIL_RAG_MAX_SCAN`, capped at 10,000), so older indexed mail is not silently excluded by the previous 1,200-message retrieval window.
- The inbox schedules a delayed, non-blocking RAG sync of the latest 100 Gmail messages. It does not delay inbox rendering and existing indexed message IDs are skipped. This keeps new/current mail available to Ask Email-AI without requiring a manual full-history sync every time.
- PostgreSQL compatibility connection now exposes rollback for safer transaction recovery in future DB operations.

No company/sender-specific classification rules were added. Existing Communication Brain, OAuth, reply, reminder, attachment and semantic classification wiring was left unchanged.
