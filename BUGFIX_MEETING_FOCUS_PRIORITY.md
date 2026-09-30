# Meeting, Focus, and Priority Bug Fix

This patch keeps the existing wiring and Unified Communication Brain architecture.

## Fixed
- Focus no longer spends dashboard slots on Brain-classified JOB_FEED, MARKETING, SOCIAL, or AUTOMATED_LOW_VALUE messages. They remain available in Updates / All Mail and persisted data.
- No sender/domain/keyword promotional rules were added.
- Reply lifecycle now prefers factual ICS DTSTART/DTEND over stale attachment prose or generic body time parsing.
- Ended ICS meetings with unknown attendance use the same human-in-the-loop ended-meeting flow used by Nous.
- Future availability/RSVP flow only runs when the grounded event start is actually in the future.
- Attachment analysis no longer adds numeric priority boosts to the message priority in the UI. The Communication Brain remains the single semantic priority authority.

## Validation
- `python -m compileall backend/app`: PASS
- `PYTHONPATH=backend python -m pytest backend/tests/test_human_brain_architecture.py backend/tests/test_calendar_lifecycle_regression.py -q`: 8 passed
- Frontend build: NOT RUN in packaging environment because node_modules are intentionally absent. Run `npm install` then `npm run build` locally before commit.

## Scope note
Existing stale Neon semantics can still require the semantic-version background repair already included in this source. This patch does not wipe Neon.
