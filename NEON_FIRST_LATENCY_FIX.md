# Neon-first inbox latency correction

This build keeps the Unified Communication Brain / Ask Email-AI / meeting lifecycle work, but changes the inbox serving path so Gmail and LLM work do not block an already-populated mailbox.

- `/inbox` reads processed rows from Neon first.
- Existing cached rows are not synchronously re-triaged on app load.
- Gmail discovery runs after the response in a background task.
- Only Gmail IDs not already persisted are metadata-fetched and Brain-triaged.
- Full MIME/ICS fetch is restricted to newly discovered messages; the old up-to-60 recent-message deep pass is removed from inbox refresh.
- Focus does not use a numeric threshold or keyword/company rule; it returns the requested number from the Brain-ranked cached candidate pool when enough candidates exist.
- Empty Neon uses a bounded 20-30 message bootstrap only for a brand-new workspace.

This is a serving/synchronization correction, not a change to the Human-in-the-loop semantic policy.
