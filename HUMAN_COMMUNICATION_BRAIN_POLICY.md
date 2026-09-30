# Human Communication Brain Policy

## Product principle

Email-AI has one semantic authority: the Communication Brain. Semantic meaning is not decided by sender/domain lists, keywords, numeric priority thresholds, or separate legacy scoring engines.

The Brain reads the communication as a human assistant would: message body, recent thread, sender/recipient role, attachment intelligence, calendar evidence, timing, unresolved requests, consequence, relationship evidence, and current context. It judges which messages deserve attention **now**, not which messages merely contain an “important” word.

## What “important to the user” means

There is no fixed formula. The Brain weighs the whole situation. Direct human communication, meaningful consequences, unresolved actions, deadlines, security/account events, important work/personal context, meeting changes, and recent developments can matter. Bulk or automated mail can still be important when the consequence is important. A direct recruiter message can matter more than a job digest; a cancellation can matter more than an older invitation. Recency is part of context, not a hard override.

`inbox_score` is the Brain's comparative attention judgment. Focus sorts the recent Primary + Spam candidate pool by that judgment and returns the requested number. Code does not convert priority percentages into Focus membership.

## Unified / Communication / AI Brain

“Unified” means every semantic path uses the same Brain contract: dashboard triage, deep analysis, background ingestion, meetings/follow-ups discovery, and legacy async analysis. This prevents one engine calling an email Personal while another calls it Work or Meeting.

The Brain returns structured judgments so the product remains predictable: relationship, intent, importance, attention score, action/reply need, meeting relation, follow-up need, known facts, unknown facts, confidence, and reasons.

## Human in the loop

The Brain must not invent user-owned facts. If a consequential action depends on something it cannot know—personal availability, whether the user attended an ended meeting, whether they want to accept/reschedule, or another ambiguous decision—it asks the user. Unknown is a valid state.

## Deterministic code is limited to facts and integrity

Code may parse and preserve objective evidence such as Gmail labels, authenticated identity, ICS UID/DTSTART/DTEND/STATUS, timestamps/timezones, database ownership, deduplication, and explicit credential exposure. These facts constrain hallucination but do not decide semantic importance or relationship.

A calendar file saying `STATUS:CANCELLED` is evidence supplied to the Brain/system; it is not a sender-specific semantic rule. Likewise, `event_end < now` establishes that the scheduled time ended, but it does not establish that the user missed the meeting.

## Reminders

There is no universal “15 minutes before” rule. Meeting persistence and reminder persistence are separate. A reminder must come from explicit calendar evidence, a grounded Communication Brain judgment, or a user choice. The system does not invent reminder times.
