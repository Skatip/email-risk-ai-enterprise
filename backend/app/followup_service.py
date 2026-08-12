from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from app.db import connect


def _now() -> int:
    return int(time.time())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_status(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    status = status.strip().lower()
    allowed = {"pending", "due", "missed", "done", "dismissed", "snoozed"}
    return status if status in allowed else None


def _missed_grace_seconds() -> int:
    return max(60, min(_safe_int(os.getenv("REMINDER_MISSED_GRACE_SECONDS", "900"), 900), 24 * 3600))


def _refresh_temporal_states(cur, user_id: str, now: int) -> None:
    # A reminder becomes due as soon as its reminder time passes.
    cur.execute(
        """UPDATE followup_reminders SET status='due', triggered_at=COALESCE(triggered_at, ?)
           WHERE user_id=? AND status IN ('pending','snoozed') AND remind_at <= ?""",
        (now, user_id, now),
    )
    # A meeting/deadline becomes missed shortly after the actual event time passes.
    grace = _missed_grace_seconds()
    cur.execute(
        """UPDATE followup_reminders SET status='missed', triggered_at=COALESCE(triggered_at, ?)
           WHERE user_id=? AND status IN ('pending','due','snoozed')
             AND COALESCE(event_at, remind_at) > 0
             AND COALESCE(event_at, remind_at) + ? < ?""",
        (now, user_id, grace, now),
    )


def create_followup(
    email_id: str,
    remind_at: Any,
    note: str = "",
    thread_id: str = "",
    subject: str = "",
    sender: str = "",
    provider: str = "gmail",
    user_id: str = "",
    event_at: Any = 0,
    event_timezone: str = "",
    reminder_kind: str = "email",
) -> Dict[str, Any]:
    if not email_id:
        raise ValueError("email_id is required")
    if not user_id:
        raise ValueError("user_id is required")
    remind_ts = _safe_int(remind_at)
    if remind_ts <= 0:
        remind_ts = _now() + 3600
    event_ts = _safe_int(event_at)

    conn = connect(); cur = conn.cursor()
    existing = cur.execute(
        """SELECT * FROM followup_reminders
           WHERE user_id=? AND email_id=? AND status IN ('pending','due','missed','snoozed')
           ORDER BY remind_at ASC LIMIT 1""",
        (user_id, email_id),
    ).fetchone()
    if existing:
        # Correct previously stored guessed times when a grounded event time is now known.
        if event_ts > 0:
            cur.execute(
                """UPDATE followup_reminders
                   SET remind_at=?, event_at=?, event_timezone=?, reminder_kind=?, note=?
                   WHERE id=? AND user_id=?""",
                (remind_ts, event_ts, event_timezone or "", reminder_kind or "email", note or existing.get("note", ""), existing["id"], user_id),
            )
            _refresh_temporal_states(cur, user_id, _now())
            conn.commit()
            existing = cur.execute("SELECT * FROM followup_reminders WHERE id=? AND user_id=?", (existing["id"], user_id)).fetchone()
        conn.close()
        return {"status": "exists", "followup": dict(existing)}

    cur.execute(
        """INSERT INTO followup_reminders(
            user_id,email_id,thread_id,remind_at,status,note,created_at,
            subject,sender,provider,triggered_at,completed_at,event_at,event_timezone,reminder_kind
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, email_id, thread_id or "", remind_ts, "pending", note or "", _now(), subject or "", sender or "", provider or "gmail", None, None, event_ts or None, event_timezone or "", reminder_kind or "email"),
    )
    new_id = cur.lastrowid
    _refresh_temporal_states(cur, user_id, _now())
    conn.commit()
    row = cur.execute("SELECT * FROM followup_reminders WHERE id=? AND user_id=?", (new_id, user_id)).fetchone()
    conn.close()
    return {"status": "created", "followup": dict(row)}


def list_followups(user_id: str, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    conn = connect(); cur = conn.cursor(); now = _now()
    _refresh_temporal_states(cur, user_id, now); conn.commit()
    limit = max(1, min(_safe_int(limit, 100), 500))
    status = _normalize_status(status)
    if status:
        rows = cur.execute(
            "SELECT * FROM followup_reminders WHERE user_id=? AND status=? ORDER BY COALESCE(event_at,remind_at) ASC LIMIT ?",
            (user_id, status, limit),
        ).fetchall()
    else:
        rows = cur.execute(
            """SELECT * FROM followup_reminders WHERE user_id=?
               ORDER BY CASE status WHEN 'missed' THEN 0 WHEN 'due' THEN 1 WHEN 'pending' THEN 2 WHEN 'snoozed' THEN 3 WHEN 'done' THEN 4 ELSE 5 END,
               COALESCE(event_at,remind_at) ASC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_due_followups(user_id: str, mark_due: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    now = _now(); conn = connect(); cur = conn.cursor()
    limit = max(1, min(_safe_int(limit, 100), 500))
    if mark_due:
        _refresh_temporal_states(cur, user_id, now); conn.commit()
    rows = cur.execute(
        """SELECT * FROM followup_reminders
           WHERE user_id=? AND status IN ('due','missed')
           ORDER BY COALESCE(event_at,remind_at) ASC LIMIT ?""",
        (user_id, limit),
    ).fetchall(); conn.close()
    return [dict(r) for r in rows]


def update_followup_status(followup_id: Any, status: str, user_id: str) -> Dict[str, Any]:
    allowed = {"pending", "due", "missed", "done", "dismissed", "snoozed"}
    status = (status or "").strip().lower()
    if status not in allowed:
        raise ValueError(f"status must be one of {sorted(allowed)}")
    if not user_id:
        raise ValueError("user_id is required")
    fid = _safe_int(followup_id)
    completed_at = _now() if status in {"done", "dismissed"} else None
    conn = connect(); cur = conn.cursor()
    cur.execute("UPDATE followup_reminders SET status=?, completed_at=? WHERE id=? AND user_id=?", (status, completed_at, fid, user_id))
    conn.commit(); row = cur.execute("SELECT * FROM followup_reminders WHERE id=? AND user_id=?", (fid, user_id)).fetchone(); conn.close()
    if not row:
        raise ValueError("followup not found")
    return {"status": "updated", "followup": dict(row)}


def snooze_followup(followup_id: Any, user_id: str, seconds: int = 3600) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    fid = _safe_int(followup_id)
    seconds = max(60, min(_safe_int(seconds, 3600), 30 * 24 * 3600))
    conn = connect(); cur = conn.cursor()
    cur.execute(
        """UPDATE followup_reminders SET status='snoozed', remind_at=?, triggered_at=NULL, completed_at=NULL
           WHERE id=? AND user_id=?""",
        (_now() + seconds, fid, user_id),
    ); conn.commit()
    row = cur.execute("SELECT * FROM followup_reminders WHERE id=? AND user_id=?", (fid, user_id)).fetchone(); conn.close()
    if not row:
        raise ValueError("followup not found")
    return {"status": "snoozed", "followup": dict(row)}


def suggest_followup_from_brain(brain_result: Dict[str, Any]) -> Dict[str, Any]:
    """Use Communication Brain output directly; no keyword rules."""
    result = brain_result or {}
    follow = result.get("follow_up") or {}
    commitments = result.get("commitments") or []
    decision = str(result.get("decision") or "").upper()
    should = bool(follow.get("needed") or follow.get("should_create") or commitments or decision in {"DRAFT_AND_ACTION", "ACTION_ONLY"})
    return {
        "should_create": should,
        "reason": follow.get("reason") or result.get("understanding") or "",
        "suggested_remind_at": follow.get("remind_at_unix") or follow.get("remind_at") or follow.get("suggested_remind_at"),
        "note": follow.get("note") or "Follow up on this conversation.",
        "commitments": commitments,
    }
