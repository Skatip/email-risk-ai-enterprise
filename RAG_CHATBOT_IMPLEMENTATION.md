# Ask Email-AI — Neon RAG chatbot

Implemented on top of the latency/Neon build.

- `/rag/sync` backfills old/current Gmail into a user-isolated Neon RAG table.
- Email bodies are embedded with the existing OpenAI embedding provider.
- `/rag/ask` performs hybrid semantic + lexical retrieval and sends only top evidence to the LLM.
- Answers are instructed to use only retrieved evidence and expose source email subject/sender/date.
- Retrieved email text is treated as untrusted evidence, not instructions (prompt-injection boundary).
- Existing inbox/reply/Communication Brain wiring is unchanged.
- Sync is incremental by Gmail message ID and RAG version; already indexed messages are not re-embedded.
- Default manual history sync is 500 messages and can be increased server-side up to 5000.

This version intentionally uses JSONB embeddings plus bounded hybrid scoring for compatibility with the existing Neon database. A pgvector/HNSW migration should be introduced only when index size/latency measurements justify it.
