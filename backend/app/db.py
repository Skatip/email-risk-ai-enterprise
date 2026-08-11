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
        """CREATE TABLE IF NOT EXISTS sender_stats(
            sender_email TEXT PRIMARY KEY, sender_name TEXT, total_count INTEGER DEFAULT 0,
            high_count INTEGER DEFAULT 0, medium_count INTEGER DEFAULT 0, low_count INTEGER DEFAULT 0,
            avg_priority DOUBLE PRECISION DEFAULT 0, last_seen_ts BIGINT DEFAULT 0,
            vip INTEGER DEFAULT 0, blocked INTEGER DEFAULT 0)""",
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


def upsert_sender(sender_email: str, sender_name: str, priority: float, label: str, ts: int) -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute("SELECT * FROM sender_stats WHERE sender_email=?", (sender_email,)); row = cur.fetchone()
    high, med, low = int(label == "HIGH"), int(label == "MEDIUM"), int(label == "LOW")
    if not row:
        cur.execute("INSERT INTO sender_stats(sender_email,sender_name,total_count,high_count,medium_count,low_count,avg_priority,last_seen_ts) VALUES(?,?,?,?,?,?,?,?)", (sender_email, sender_name, 1, high, med, low, float(priority), int(ts)))
    else:
        total = int(row["total_count"]) + 1
        new_avg = float(row["avg_priority"]) + (float(priority) - float(row["avg_priority"])) / total
        cur.execute("UPDATE sender_stats SET sender_name=?,total_count=?,high_count=high_count+?,medium_count=medium_count+?,low_count=low_count+?,avg_priority=?,last_seen_ts=GREATEST(last_seen_ts,?) WHERE sender_email=?", (sender_name, total, high, med, low, new_avg, int(ts), sender_email))
    conn.commit(); conn.close()


def set_sender_flag(sender_email: str, vip: Optional[int] = None, blocked: Optional[int] = None) -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute("INSERT INTO sender_stats(sender_email) VALUES(?) ON CONFLICT(sender_email) DO NOTHING", (sender_email,))
    if vip is not None: cur.execute("UPDATE sender_stats SET vip=? WHERE sender_email=?", (int(vip), sender_email))
    if blocked is not None: cur.execute("UPDATE sender_stats SET blocked=? WHERE sender_email=?", (int(blocked), sender_email))
    conn.commit(); conn.close()


def get_sender(sender_email: str) -> Optional[Dict[str, Any]]:
    conn = connect(); cur = conn.cursor(); cur.execute("SELECT * FROM sender_stats WHERE sender_email=?", (sender_email,)); row = cur.fetchone(); conn.close(); return dict(row) if row else None


def top_senders(limit: int = 20) -> List[Dict[str, Any]]:
    conn = connect(); cur = conn.cursor(); cur.execute("SELECT sender_email,sender_name,total_count,high_count,avg_priority,vip,blocked FROM sender_stats ORDER BY high_count DESC,avg_priority DESC,total_count DESC LIMIT ?", (limit,)); rows = cur.fetchall(); conn.close(); return [dict(r) for r in rows]
