# Email-AI verified bug-fix pass — 2026-09-29

Base: the clean project ZIP uploaded by the user on 2026-09-29.

## Fixed in this pass
- Focus/Important now excludes LOW items and uses newest-first qualified results.
- Unseen Gmail candidates are triaged newest-first in bounded chunks; once the requested Focus count is satisfied, older unseen mail is not analyzed on the critical path. Repeat loads make zero new triage calls when the known newest prefix already satisfies the requested count.
- Meeting candidate detection now accepts semantic SCHEDULE/INVITE/INTERVIEW/SESSION intents, `.ics` / `text/calendar`, and generic meeting/invitation subject evidence. No company/domain-specific meeting rules were added.
- Background meeting persistence no longer runs a second deep LLM analysis. It uses grounded subject/ICS evidence after inbox response.
- `.ics` DTSTART/DTEND/TZID remains authoritative.
- Future meeting reminders are persisted separately from meetings.
- RSVP/action follow-ups are persisted separately from meeting reminders only when triage says action/reply is owed.
- `create_followup` de-duplication now includes `reminder_kind`, allowing one email to have a Meeting reminder and a separate Follow-up without overwriting each other.
- Past meetings are persisted in Meetings but do not get newly-created pre-meeting reminders.
- Persisted meeting lifecycle is overlaid onto inbox cards before opening the email; past meetings become PAST_EVENT and cannot offer a future-attendance reply.
- Added a dedicated Reminders UI surface; Meetings, Reminders, and Follow-ups are separate.
- Strengthened semantic prompt against labeling workplace/team meeting invitations as Family/Personal without positive personal-relationship evidence.
- Removed the unused Yahoo OAuth integration module. Generic @yahoo.com sender classification remains because Gmail can receive mail from Yahoo addresses.

## Tests actually run
- Python compileall: PASS.
- Local deterministic regression tests: 6/6 PASS.
  - explicit Sep 28 meeting date grounding
  - ICS timezone and 30-minute end time
  - SCHEDULE intent meeting detection
  - generic invitation subject meeting detection
  - LOW email exclusion from Focus
  - HIGH actionable email inclusion in Focus
- Frontend production build: NOT CLAIMED. `npm install` exceeded the available execution window before Vite became available.

## Deployment validation still required
Live Gmail/Google OAuth, Neon, OpenAI, and browser behavior require the user's real environment and credentials. After deployment verify the Sep 28 Nous invitation and Abhishek ICS invitation appear in Meetings without opening them, Focus 10 contains no LOW cards, and repeat inbox loads reuse persisted triage.
