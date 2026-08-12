# Reminder + Calendar Chronology Fix

This patch preserves the restored inbox/analytics behavior and makes only targeted scheduling/reminder changes.

- Grounds explicit meeting times such as `5pm PST today` from the real email text instead of trusting an LLM-guessed reminder timestamp.
- Stores both the reminder time and actual event time in the existing PostgreSQL/Neon follow-up table using safe additive columns.
- Reminder lifecycle now updates while the app is open: pending/upcoming -> due -> missed/overdue. Default missed grace is 15 minutes.
- Frontend refreshes reminder state every 30 seconds and shows an in-app upcoming/due/missed banner. No Celery or Redis is required.
- Meeting replies cannot be drafted before user availability is explicitly confirmed. A free calendar only means no detected conflict.
- For scheduling emails, the backend deterministically checks Google Calendar read-only for the grounded requested time, then asks the user Yes/No before drafting.
- Pre-generated meeting acceptance text is hidden until user confirmation.
- Attachment document intelligence no longer leaks email-context dates/actions into attachment facts; generic verb actions and false invoice/payment actions were reduced.

Optional Render settings:
- `MEETING_REMINDER_LEAD_SECONDS=900` (default 15 minutes before event)
- `REMINDER_MISSED_GRACE_SECONDS=900` (default 15 minutes after event)

Existing Gmail/Calendar OAuth and Uvicorn deployment are preserved.
