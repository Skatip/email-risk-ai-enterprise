# Abhishek meeting ingestion correction — 2026-09-29

Evidence: Gmail Primary contains both `Practice session for Sandeep` and a later `Canceled: Practice session for Sandeep`, while Email-AI Meetings showed Nous events but not the Abhishek event.

Root cause verified in code:
- Fast Gmail discovery used `format=metadata`. Gmail metadata responses do not provide the MIME attachment structure needed to discover an ICS reliably.
- The background temporal job only deep-fetched messages already judged meeting/follow-up by lightweight triage. Therefore an email whose meeting evidence lived in `invite.ics` could remain invisible until the user opened it.
- Calendar cancellation/UID/SEQUENCE were not persisted, so updates/cancellations could not reconcile the original event robustly.

Corrections:
- Recent Primary+Spam messages are full-fetched in a bounded background ingestion pass after the inbox response; richer metadata is persisted without requiring a click.
- Calendar MIME parts are recognized whether Gmail supplies `attachmentId` or inline `body.data`.
- ICS parsing now returns UID, METHOD, STATUS, SEQUENCE, start and end.
- Calendar UID is used as the stable event identity across invite/update/cancel messages.
- Newer cancellation state cannot be reopened by an older invitation.
- Canceled meetings dismiss their pre-meeting reminders.
- Meeting lifecycle uses DTEND when available.
- Meeting UI renders browser-local time without attaching the source timezone label to a converted local clock time.
- Focus returns the requested number of Brain-ranked recent Primary+Spam candidates instead of requiring a fixed `IMPORTANT_NOW` bucket.

Validation performed here:
- Python compileall: PASS.
- Calendar lifecycle regression tests: 2/2 PASS (cancelled ICS UID/SEQUENCE/end-time and normal confirmed ICS).
- Frontend production build: NOT CLAIMED. `npm install` exceeded the execution window before dependencies were available.
- Live Gmail/Neon end-to-end: NOT CLAIMED because this environment does not have the user's OAuth/Neon credentials.
