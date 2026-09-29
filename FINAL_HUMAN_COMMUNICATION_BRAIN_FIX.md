# Final human-context Communication Brain revision — 2026-09-29

This build is based on the user's clean source ZIP.

## Behavior corrected
- Gmail source scope remains Primary + Spam for the recent 7-day candidate window. Promotions/Social/Forums are not intentionally substituted for Primary.
- Focus is selected by the Communication Brain's contextual `IMPORTANT_NOW` judgment and attention score, not sender/domain/keyword/priority thresholds.
- Semantic triage now explicitly returns `meeting_related` and `follow_up_needed`; background persistence uses those AI judgments rather than meeting/deadline keyword lists.
- Calendar/ICS attachments remain factual evidence and can create meeting candidates even before an email is opened.
- Meetings, reminders and follow-ups are persisted independently. A conversational follow-up may exist without an invented reminder time.
- Past meetings do not get a new pre-meeting reminder.
- Past meeting reply flow is human-in-the-loop: if attendance is unknown, ask whether the user attended, missed it, or needs no action. Never claim future attendance for a past event.
- Future scheduling still requires calendar conflict check plus explicit user availability confirmation before an acceptance reply.
- Semantic post-processing no longer rewrites professional/personal relationship, reply ownership, Focus, or priority using hard-coded business rules. Deterministic handling is limited to factual metadata and exposed-secret safety evidence.
- Analysis version bumped to `semantic-v3-human-context` so stale cached v2 judgments are re-triaged.
- Unused Yahoo OAuth provider file removed; ordinary Yahoo sender addresses remain valid Gmail content.

## Validation performed here
- Python `compileall` for backend/app: PASS.
- Deterministic explicit-date parse regression: PASS.
- ICS DTSTART/DTEND/TZID 30-minute event regression: PASS.
- Full pytest could not be executed in this environment because the OpenAI Python package is not installed and outbound package installation is unavailable.
- Frontend npm production build was not claimed here because dependencies are intentionally excluded from the clean source ZIP.

## Production validation still required
With your own `.env`, Google OAuth, Neon and OpenAI credentials, verify against the real mailbox: recent Primary+Spam Focus selection, Sep 28 Nous, Abhishek Practice Session, Meetings/Reminders/Follow-ups before opening the email, past-meeting human confirmation, and repeated refresh stability.
