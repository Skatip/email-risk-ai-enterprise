from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required. Use a Neon PostgreSQL connection string.")
    return url


class CursorCompat:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params=()):
        self._cursor.execute(self._sql(sql), params)
        if sql.lstrip().upper().startswith("INSERT"):
            try:
                self._cursor.execute("SELECT LASTVAL() AS id")
                row = self._cursor.fetchone()
                self.lastrowid = row["id"] if row else None
            except Exception:
                self.lastrowid = None
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class ConnectionCompat:
    def __init__(self):
        self._conn = psycopg.connect(_database_url(), row_factory=dict_row)

    def cursor(self):
        return CursorCompat(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def connect() -> ConnectionCompat:
    return ConnectionCompat()


def init_db() -> None:
    conn = connect()
    cur = conn.cursor()
    statements = [
        """CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)""",
        """CREATE TABLE IF NOT EXISTS followup_reminders(
            id BIGSERIAL PRIMARY KEY, user_id TEXT DEFAULT '', email_id TEXT, thread_id TEXT,
            remind_at BIGINT, status TEXT DEFAULT 'pending', note TEXT, created_at BIGINT,
            subject TEXT, sender TEXT, provider TEXT DEFAULT 'gmail', triggered_at BIGINT, completed_at BIGINT)""",
        """CREATE TABLE IF NOT EXISTS email_events(
            id BIGSERIAL PRIMARY KEY, user_id TEXT DEFAULT '', email_id TEXT, event_type TEXT,
            metadata TEXT, created_at BIGINT)""",
        """CREATE TABLE IF NOT EXISTS thread_summaries(
            thread_id TEXT PRIMARY KEY, user_id TEXT DEFAULT '', summary TEXT, state_json JSONB DEFAULT '{}'::jsonb,
            last_message_id TEXT, created_at BIGINT, updated_at BIGINT)""",
        """CREATE TABLE IF NOT EXISTS communication_memory(
            id BIGSERIAL PRIMARY KEY, user_id TEXT NOT NULL, contact_key TEXT, memory_type TEXT,
            content JSONB NOT NULL, confidence DOUBLE PRECISION DEFAULT 1, created_at BIGINT, updated_at BIGINT)""",
        """CREATE TABLE IF NOT EXISTS ai_usage(
            id BIGSERIAL PRIMARY KEY, user_id TEXT, feature TEXT, model TEXT,
            input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
            estimated_cost DOUBLE PRECISION DEFAULT 0, latency_ms INTEGER DEFAULT 0, created_at BIGINT)""",
        """CREATE TABLE IF NOT EXISTS audit_logs(
            id BIGSERIAL PRIMARY KEY, user_id TEXT, action TEXT, resource_type TEXT,
            resource_id TEXT, metadata JSONB DEFAULT '{}'::jsonb, created_at BIGINT)""",
        """CREATE TABLE IF NOT EXISTS inbox_intelligence_cache(
            user_id TEXT NOT NULL, email_id TEXT NOT NULL, semantic_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at BIGINT NOT NULL, PRIMARY KEY(user_id, email_id))""",
        "CREATE INDEX IF NOT EXISTS idx_inbox_intelligence_user_updated ON inbox_intelligence_cache(user_id, updated_at DESC)",
    ]
    for statement in statements:
        cur.execute(statement)
    conn.commit()
    conn.close()


def kv_get(key: str) -> Optional[str]:
    conn = connect(); cur = conn.cursor(); cur.execute("SELECT v FROM kv WHERE k=?", (key,)); row = cur.fetchone(); conn.close()
    return row["v"] if row else None


def kv_set(key: str, value: str) -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v", (key, value))
    conn.commit(); conn.close()
