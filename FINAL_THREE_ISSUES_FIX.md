# Final three-issue correction

## 1. Dashboard latency
- Background reconciliation is now limited to true temporal candidates (meeting/calendar/appointment/payment/deadline), rather than every actionable/reply email.
- The background task yields after the inbox response and processes a bounded set, reducing contention with the visible inbox.
- Persisted Neon semantic results remain reused; no progressive/incomplete inbox UI was introduced.

## 2. Meeting questions / missed meetings
- Ask Email-AI now receives the browser's IANA timezone and interprets today/yesterday in the user's timezone rather than server UTC or the meeting's source timezone.
- Explicit dates such as Sep 28, 2026 and 28th September 2026 are deterministically filtered before generation.
- Structured meeting queries no longer append unrelated vector-search sources when structured evidence exists.
- Duplicate invitation email sources are not used to count meetings.
- `past_unknown` is explicitly not proof of a missed meeting. Confirmed missed and attendance-unknown past meetings are distinguished.
- Unix timestamps are internal only and must not appear in user-facing answers.

## 3. Past meetings asking for input
- A meeting whose grounded event time is already past produces no RSVP/availability question.
- No future-attendance draft is generated.
- The state remains past/attendance unknown until actual attendance evidence is available.

## Timezone principle
Event source timezone is preserved for the event itself, while words such as today/yesterday are evaluated in the user's browser/device IANA timezone. This avoids hardcoding Pacific, Eastern, or any other person's timezone.
