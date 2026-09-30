from __future__ import annotations
import time
from typing import Any, Dict, List
from app.db import connect

MEETING_KINDS = {"meeting", "calendar", "appointment"}

def init_obligations() -> None:
    conn=connect(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS email_obligations(
      user_id TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'gmail', email_id TEXT NOT NULL,
      thread_id TEXT DEFAULT '', kind TEXT NOT NULL, title TEXT DEFAULT '', source_sender TEXT DEFAULT '',
      due_at BIGINT DEFAULT 0, event_end_at BIGINT DEFAULT 0, timezone TEXT DEFAULT '', state TEXT NOT NULL DEFAULT 'upcoming',
      attendance_status TEXT NOT NULL DEFAULT 'unknown', evidence TEXT DEFAULT '', confidence DOUBLE PRECISION DEFAULT 0,
      event_uid TEXT DEFAULT '', source_ts BIGINT DEFAULT 0, calendar_sequence INTEGER DEFAULT 0,
      updated_at BIGINT NOT NULL, PRIMARY KEY(user_id,provider,email_id,kind)
    )""")
    for sql in (
        "ALTER TABLE email_obligations ADD COLUMN IF NOT EXISTS event_end_at BIGINT DEFAULT 0",
        "ALTER TABLE email_obligations ADD COLUMN IF NOT EXISTS event_uid TEXT DEFAULT ''",
        "ALTER TABLE email_obligations ADD COLUMN IF NOT EXISTS source_ts BIGINT DEFAULT 0",
        "ALTER TABLE email_obligations ADD COLUMN IF NOT EXISTS calendar_sequence INTEGER DEFAULT 0",
    ):
        cur.execute(sql)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obligations_user_due ON email_obligations(user_id,due_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obligations_user_uid ON email_obligations(user_id,provider,event_uid)")
    conn.commit(); conn.close()

def upsert_from_followup(user_id:str,email:Dict[str,Any],timing:Dict[str,Any],semantic:Dict[str,Any],provider:str='gmail')->None:
    if not user_id or not email.get('id'): return
    kind=str(timing.get('reminder_kind') or 'email').lower()
    if kind not in MEETING_KINDS:
        intent=str(semantic.get('intent') or '').upper()
        kind='deadline' if any(x in intent for x in ('PAYMENT','DEADLINE','DUE','DOCUMENT_REVIEW')) else 'task'
    due=int(timing.get('event_at') or timing.get('remind_at') or 0); now=int(time.time())
    end_at=int(timing.get('event_end_at') or due or 0)
    event_uid=str(timing.get('event_uid') or '').strip()
    source_ts=int(email.get('ts') or 0)
    sequence=int(timing.get('calendar_sequence') or 0)
    cancelled=bool(timing.get('cancelled'))
    state='cancelled' if cancelled else ('upcoming' if end_at>now else ('past_unknown' if kind in MEETING_KINDS else 'overdue'))
    conn=connect(); cur=conn.cursor()

    # Calendar UID is the stable identity across invitation/update/cancellation emails.
    # A newer update may replace an older state; an older invitation must never reopen
    # a cancellation that arrived later.
    if kind in MEETING_KINDS and event_uid:
        existing=cur.execute("""SELECT * FROM email_obligations
            WHERE user_id=? AND provider=? AND event_uid=? AND kind IN ('meeting','calendar','appointment')
            ORDER BY source_ts DESC, calendar_sequence DESC, updated_at DESC LIMIT 1""",
            (user_id,provider,event_uid)).fetchone()
        if existing:
            existing_ts=int(existing.get('source_ts') or 0); existing_seq=int(existing.get('calendar_sequence') or 0)
            if source_ts < existing_ts or (source_ts == existing_ts and sequence < existing_seq):
                conn.close(); return
            cur.execute("""UPDATE email_obligations SET email_id=?,thread_id=?,kind=?,title=?,source_sender=?,due_at=?,event_end_at=?,timezone=?,state=?,
                attendance_status=CASE WHEN ?='cancelled' THEN attendance_status ELSE attendance_status END,
                evidence=?,confidence=?,source_ts=?,calendar_sequence=?,updated_at=?
                WHERE user_id=? AND provider=? AND event_uid=?""",
                (str(email.get('id')),str(email.get('threadId') or ''),kind,str(email.get('subject') or ''),str(email.get('from') or ''),due,end_at,
                 str(timing.get('event_timezone') or ''),state,state,str(semantic.get('reason') or semantic.get('priority_reason') or '')[:700],
                 float(semantic.get('confidence') or 0),source_ts,sequence,now,user_id,provider,event_uid))
            conn.commit(); conn.close(); return

    cur.execute("""INSERT INTO email_obligations(user_id,provider,email_id,thread_id,kind,title,source_sender,due_at,event_end_at,timezone,state,attendance_status,evidence,confidence,event_uid,source_ts,calendar_sequence,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(user_id,provider,email_id,kind) DO UPDATE SET thread_id=EXCLUDED.thread_id,title=EXCLUDED.title,source_sender=EXCLUDED.source_sender,
      due_at=EXCLUDED.due_at,event_end_at=EXCLUDED.event_end_at,timezone=EXCLUDED.timezone,state=EXCLUDED.state,evidence=EXCLUDED.evidence,
      confidence=EXCLUDED.confidence,event_uid=EXCLUDED.event_uid,source_ts=EXCLUDED.source_ts,calendar_sequence=EXCLUDED.calendar_sequence,updated_at=EXCLUDED.updated_at""",
      (user_id,provider,str(email.get('id')),str(email.get('threadId') or ''),kind,str(email.get('subject') or ''),str(email.get('from') or ''),due,end_at,
       str(timing.get('event_timezone') or ''),state,'unknown',str(semantic.get('reason') or semantic.get('priority_reason') or '')[:700],
       float(semantic.get('confidence') or 0),event_uid,source_ts,sequence,now))
    conn.commit(); conn.close()

def query_obligations(user_id:str,limit:int=50)->List[Dict[str,Any]]:
    if not user_id:return []
    conn=connect(); cur=conn.cursor(); now=int(time.time())
    cur.execute("""UPDATE email_obligations SET state='past_unknown',updated_at=?
        WHERE user_id=? AND kind IN ('meeting','calendar','appointment') AND state IN ('upcoming','due')
          AND COALESCE(NULLIF(event_end_at,0),due_at)>0 AND COALESCE(NULLIF(event_end_at,0),due_at)<?""",(now,user_id,now))
    cur.execute("UPDATE email_obligations SET state='overdue',updated_at=? WHERE user_id=? AND kind NOT IN ('meeting','calendar','appointment') AND due_at>0 AND due_at<? AND state IN ('upcoming','due')",(now,user_id,now)); conn.commit()
    rows=cur.execute("SELECT * FROM email_obligations WHERE user_id=? ORDER BY due_at DESC LIMIT ?",(user_id,max(1,min(limit,200)))).fetchall(); conn.close()
    return [dict(r) for r in rows]
