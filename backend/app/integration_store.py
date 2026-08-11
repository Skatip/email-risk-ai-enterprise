from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

import psycopg
from cryptography.fernet import Fernet
from psycopg.rows import dict_row


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required for hosted OAuth storage")
    return value


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "").encode()
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required")
    return Fernet(key)


def init_integration_store() -> None:
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS oauth_states(
                state_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                expires_at BIGINT NOT NULL,
                created_at BIGINT NOT NULL
            )""")
            cur.execute("""CREATE TABLE IF NOT EXISTS integration_connections(
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                account_email TEXT,
                encrypted_credentials TEXT NOT NULL,
                scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
                status TEXT NOT NULL DEFAULT 'connected',
                sync_cursor TEXT,
                last_synced_at BIGINT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                UNIQUE(user_id, provider, account_email)
            )""")
        connection.commit()


def save_connection(user_id: str, provider: str, account_email: str, credentials: Dict[str, Any], scopes: list[str]) -> None:
    init_integration_store()
    encrypted = _fernet().encrypt(json.dumps(credentials).encode()).decode()
    now = int(time.time())
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cur:
            cur.execute("""INSERT INTO integration_connections(
                user_id, provider, account_email, encrypted_credentials, scopes, status, created_at, updated_at
            ) VALUES(%s,%s,%s,%s,%s::jsonb,'connected',%s,%s)
            ON CONFLICT(user_id,provider,account_email) DO UPDATE SET
                encrypted_credentials=EXCLUDED.encrypted_credentials,
                scopes=EXCLUDED.scopes,
                status='connected',
                updated_at=EXCLUDED.updated_at""",
                (user_id, provider, account_email, encrypted, json.dumps(scopes), now, now),
            )
        connection.commit()


def get_connection(user_id: str, provider: str, account_email: str | None = None) -> Optional[Dict[str, Any]]:
    init_integration_store()
    query = "SELECT * FROM integration_connections WHERE user_id=%s AND provider=%s AND status='connected'"
    params: list[Any] = [user_id, provider]
    if account_email:
        query += " AND account_email=%s"
        params.append(account_email)
    query += " ORDER BY updated_at DESC LIMIT 1"
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        with connection.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
    if not row:
        return None
    item = dict(row)
    item["credentials"] = json.loads(_fernet().decrypt(item.pop("encrypted_credentials").encode()).decode())
    return item


def delete_connection(user_id: str, provider: str, account_email: str | None = None) -> None:
    init_integration_store()
    query = "UPDATE integration_connections SET status='disconnected',updated_at=%s WHERE user_id=%s AND provider=%s"
    params: list[Any] = [int(time.time()), user_id, provider]
    if account_email:
        query += " AND account_email=%s"
        params.append(account_email)
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cur:
            cur.execute(query, params)
        connection.commit()

def create_oauth_state(user_id: str, provider: str, ttl_seconds: int = 600) -> str:
    if not user_id:
        raise ValueError("user_id is required")
    init_integration_store()
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    with psycopg.connect(_database_url()) as connection:
        with connection.cursor() as cur:
            cur.execute("DELETE FROM oauth_states WHERE expires_at < %s", (now,))
            cur.execute(
                "INSERT INTO oauth_states(state_hash,user_id,provider,expires_at,created_at) VALUES(%s,%s,%s,%s,%s)",
                (digest, user_id, provider, now + max(60, int(ttl_seconds)), now),
            )
        connection.commit()
    return token


def consume_oauth_state(token: str, provider: str) -> str:
    if not token:
        raise ValueError("OAuth state is missing")
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    with psycopg.connect(_database_url(), row_factory=dict_row) as connection:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT user_id,expires_at FROM oauth_states WHERE state_hash=%s AND provider=%s",
                (digest, provider),
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM oauth_states WHERE state_hash=%s", (digest,))
        connection.commit()
    if not row or int(row["expires_at"] or 0) < now:
        raise ValueError("OAuth state is invalid or expired")
    return str(row["user_id"])

