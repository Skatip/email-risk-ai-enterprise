# Restored inbox analytics behavior

This build keeps the enterprise inbox UI cleanup while restoring the original inbox analysis behavior from the uploaded baseline.

- The inbox request waits for the bounded semantic triage batch to complete.
- The UI receives the selected important emails with priority/risk/classification analytics together, rather than progressively waiting on per-email background enrichment.
- No persistent inbox-intelligence/background polling patch is included.
- No Redis/Celery worker is required for deployment.
- The simplified enterprise inbox views remain: Focus — Important, Needs Reply, People & Conversations, Work & Career, Money & Security, Updates & Low Priority, and All Mail.
- Attachment-specific inbox buckets remain removed; attachment intelligence stays attached to each email.
