# Corrected meeting / reminder / follow-up revision

This revision keeps Meetings, Reminders, and Follow-ups separate in product behavior.

- Meetings are persisted independently in Neon and shown in a dedicated Meetings tab.
- Meeting reminders may notify the user but do not appear as Follow-ups.
- Follow-ups require explicit semantic evidence and a grounded time; the old synthetic one-hour fallback is removed.
- Security/authentication notices do not automatically become overdue follow-ups.
- Past meetings are `past_unknown` until attendance evidence exists.
- Reply generation has a deterministic past-event guard and cannot draft future attendance for an already-ended meeting.
- `.ics` attachments render as Calendar invitation instead of Project Document.
- Inbox bucket filtering now uses the full bounded candidate scan before applying the requested result limit, fixing the 50-selected/31-returned pre-filter truncation issue when enough matching messages exist.
- Background meeting/deadline discovery uses the full analyzed candidate set rather than only the currently rendered bucket.
- Legacy generic reminders created by the prior default-reminder behavior are hidden from the Follow-ups view.

Backend Python compilation passed. Frontend production build could not be completed in the execution environment because npm dependency installation exceeded the available execution window.
