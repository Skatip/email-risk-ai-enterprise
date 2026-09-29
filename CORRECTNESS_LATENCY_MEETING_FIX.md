# Correctness / latency / meeting registry fix

This revision intentionally fixes only the regressions reported after the temporal build.

- Focus returns the newest N messages that actually qualify for Focus after semantic filtering. The selected count is applied after filtering.
- Inbox in-memory cache is short-lived (8s) so stale previous result sets do not dominate refreshes.
- Gmail candidate discovery keeps a broad Primary window but a small Spam recovery window, avoiding a second full mailbox-sized scan.
- Mailbox-wide RAG sync no longer starts after every inbox load. History sync remains an explicit Ask Email-AI operation.
- Background temporal reconciliation is delayed and single-concurrency by default so it does not compete with the inbox response.
- Meeting candidate discovery accepts Communication Brain meeting/calendar/appointment/schedule/invite output, ICS/calendar attachments, and generic meeting-invitation subject evidence. The generic subject gate only triggers reconciliation; it does not itself create a meeting.
- ICS DTSTART/DTEND are parsed deterministically and used as the canonical event time when present.
- Explicit dates such as "Sep 28, 2026, 4:00 PM EST" are now honored by deterministic time grounding instead of incorrectly attaching the time to the email's sent date.
