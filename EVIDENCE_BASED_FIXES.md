# Evidence-based inbox and meeting fixes

This revision is based on the supplied Gmail/dashboard screenshots and latency video.

- Gmail discovery now scans the full Inbox window rather than only Gmail's Primary category. Gmail category labels are transport metadata; Communication Brain decides importance.
- Focus — Important filters for important messages, then returns the newest requested N qualifying messages. Selecting 10 therefore means up to 10 current qualifying Focus messages, not older high-score cards that happened to win a score sort.
- Inbox cache TTL is 8 seconds so refresh does not keep serving a stale 90-second result.
- Mailbox-wide RAG synchronization no longer starts 1.5 seconds after every inbox render. Ask Email-AI keeps its explicit history sync.
- Meetings are reconciled lazily when the Meetings surface is opened, keeping Gmail attachment work off inbox startup.
- Meeting reconciliation uses persisted semantic meeting intent and calendar (.ics/text/calendar) evidence. ICS DTSTART/DTEND/TZID are parsed deterministically and take precedence over prose.
- Explicit dates such as "Sep 28, 2026, 4:00 PM EDT" are no longer anchored to the email timestamp date.
- Meetings, reminders and follow-ups remain separate records/surfaces. Meeting reminders do not become conversational follow-ups.
- Duplicate invitation/update emails for the same event are deduplicated in the Meetings response by event time/title/sender.

Validation performed in this build:
- Python backend compilation succeeds.
- Explicit-date temporal parser test succeeds for Sep 28, 2026 at 4:00 PM EDT.
- ICS parser test succeeds for DTSTART/DTEND in America/New_York and produces the expected UTC timestamp.
- Full frontend production build was attempted, but npm dependency installation exceeded the available execution window, so no frontend-build success is claimed.
