# Less-hard-rules correction

This build keeps deterministic code only for factual parsing, security boundaries, data integrity, chronology, and synchronization. Semantic meaning is owned by the Unified Communication Brain.

Changes:
- Focus no longer applies a second frontend bucket/0.38 threshold after Brain ranking.
- Removed unused legacy semantic rule modules: priority_engine, intent_extractor, sender_policy, human_signals.
- Analytics no longer recreates HIGH/MEDIUM from numeric priority thresholds; it uses Brain labels.
- Neon-first inbox serving and incremental Gmail synchronization remain.
- Full MIME/ICS fetch remains bounded to newly discovered messages, not the cached mailbox.
- Ask Email-AI, Meetings, Reminders, Follow-ups, Human-in-the-loop, RAG, and factual ICS lifecycle handling remain.
