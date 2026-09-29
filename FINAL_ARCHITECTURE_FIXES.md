# Email-AI unified intelligence revision

This build implements the architecture discussed after QA/UAT review.

- Yahoo OAuth and Yahoo UI were removed. Gmail remains active; Outlook stays disabled.
- Inbox still paints from persisted Neon intelligence. A bounded background enrichment pass now processes actionable new mail so meeting/deadline follow-ups do not depend on opening an email.
- `email_obligations` is the canonical structured store for meetings, deadlines and tasks. A passed meeting becomes `past_unknown`; it is never automatically called "missed" without attendance evidence.
- Ask Email-AI now routes meeting/deadline questions to structured obligation evidence first, then uses semantic email retrieval as supporting evidence. Weak RAG matches are filtered more aggressively and the system no longer forces six irrelevant sources. RAG version is v3.
- Link-domain mismatch is weak evidence rather than a large phishing penalty. In semantically confirmed meeting/calendar messages, an external conferencing host does not inflate risk by itself. Strong deterministic security signals such as exposed secrets remain.
- ICS evidence can classify an attachment as `Calendar Invitation` instead of `Project Document`.
- The right-side panel is simplified around meaning, recommended action, meaningful security warnings, attachments and original email. Technical AI fields are collapsed under Technical details.
- Attachment priority-boost implementation details are no longer shown in the normal UI.

Design rule: semantic understanding belongs to the Communication Brain; deterministic code owns security boundaries, time/lifecycle comparisons, OAuth, workspace isolation and send confirmation. Inbox, Follow-ups, Ask Email-AI and the UI consume the same persisted intelligence.
