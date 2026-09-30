from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterable, List

from app.db import connect

ANALYSIS_VERSION = __import__('os').getenv('INBOX_ANALYSIS_VERSION', 'semantic-v4-unified-brain')


def init_inbox_persistence() -> None:
    conn = connect(); cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS inbox_messages(
        user_id TEXT NOT NULL,
        provider TEXT NOT NULL DEFAULT 'gmail',
        email_id TEXT NOT NULL,
        thread_id TEXT,
        message_ts BIGINT DEFAULT 0,
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        semantic_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        analysis_version TEXT NOT NULL DEFAULT '',
        last_seen_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        PRIMARY KEY(user_id, provider, email_id)
    )''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_inbox_messages_user_ts ON inbox_messages(user_id, provider, message_ts DESC)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_inbox_messages_thread ON inbox_messages(user_id, provider, thread_id)')
    conn.commit(); conn.close()


def _obj(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict): return v
    if isinstance(v, str):
        try: return json.loads(v)
        except Exception: return {}
    return {}


def load_messages(user_id: str, email_ids: Iterable[str], provider: str = 'gmail') -> Dict[str, Dict[str, Any]]:
    ids = [str(x) for x in email_ids if x]
    if not user_id or not ids: return {}
    placeholders = ','.join(['?'] * len(ids))
    conn = connect(); cur = conn.cursor()
    cur.execute(f'''SELECT email_id, metadata_json, semantic_json, analysis_version
                    FROM inbox_messages
                    WHERE user_id=? AND provider=? AND email_id IN ({placeholders})''',
                (user_id, provider, *ids))
    rows = cur.fetchall(); conn.close()
    return {str(r['email_id']): {
        'metadata': _obj(r.get('metadata_json')),
        'semantic': _obj(r.get('semantic_json')),
        'analysis_version': r.get('analysis_version') or '',
    } for r in rows}


def save_metadata(user_id: str, messages: Iterable[Dict[str, Any]], provider: str = 'gmail') -> None:
    now = int(time.time()); conn = connect(); cur = conn.cursor()
    for item in messages or []:
        email_id = str(item.get('id') or '')
        if not email_id: continue
        cur.execute('''INSERT INTO inbox_messages
            (user_id,provider,email_id,thread_id,message_ts,metadata_json,semantic_json,analysis_version,last_seen_at,updated_at)
            VALUES(?,?,?,?,?,?::jsonb,'{}'::jsonb,'',?,?)
            ON CONFLICT(user_id,provider,email_id) DO UPDATE SET
              thread_id=EXCLUDED.thread_id,
              message_ts=EXCLUDED.message_ts,
              metadata_json=EXCLUDED.metadata_json,
              last_seen_at=EXCLUDED.last_seen_at,
              updated_at=EXCLUDED.updated_at''',
            (user_id, provider, email_id, item.get('threadId') or '', int(item.get('ts') or 0), json.dumps(item), now, now))
    conn.commit(); conn.close()


def save_semantics(user_id: str, semantics: Iterable[Dict[str, Any]], provider: str = 'gmail') -> None:
    now = int(time.time()); conn = connect(); cur = conn.cursor()
    for item in semantics or []:
        email_id = str(item.get('id') or '')
        if not email_id: continue
        cur.execute('''UPDATE inbox_messages SET semantic_json=?::jsonb, analysis_version=?, last_seen_at=?, updated_at=?
                       WHERE user_id=? AND provider=? AND email_id=?''',
                    (json.dumps(item), ANALYSIS_VERSION, now, now, user_id, provider, email_id))
    conn.commit(); conn.close()


def touch_messages(user_id: str, email_ids: Iterable[str], provider: str = 'gmail') -> None:
    ids = [str(x) for x in email_ids if x]
    if not user_id or not ids: return
    now = int(time.time()); placeholders = ','.join(['?'] * len(ids))
    conn = connect(); cur = conn.cursor()
    cur.execute(f'UPDATE inbox_messages SET last_seen_at=? WHERE user_id=? AND provider=? AND email_id IN ({placeholders})',
                (now, user_id, provider, *ids))
    conn.commit(); conn.close()


def load_recent_messages(user_id: str, provider: str = 'gmail', limit: int = 200) -> List[Dict[str, Any]]:
    """Return persisted metadata + semantics newest-first for reconciliation jobs."""
    if not user_id:
        return []
    conn = connect(); cur = conn.cursor()
    rows = cur.execute('''SELECT email_id, metadata_json, semantic_json, analysis_version, message_ts
                          FROM inbox_messages WHERE user_id=? AND provider=?
                          ORDER BY message_ts DESC LIMIT ?''',
                       (user_id, provider, max(1, min(int(limit), 500)))).fetchall()
    conn.close()
    out = []
    for r in rows:
        meta = _obj(r.get('metadata_json')); sem = _obj(r.get('semantic_json'))
        out.append({**meta, '_semantic': sem, '_analysis_version': r.get('analysis_version') or ''})
    return out
