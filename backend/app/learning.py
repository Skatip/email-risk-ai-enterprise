from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

LABELS = ["IMPORTANT", "LESS", "SPAM", "PROMO"]

DEFAULT_STORE_PATH = os.environ.get(
    "LEARNING_STORE_PATH",
    os.path.join(os.path.dirname(__file__), "app_data", "learning_store.json"),
)

def _now() -> int:
    return int(time.time())

def _ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)

def _load_store(path: str = DEFAULT_STORE_PATH) -> Dict[str, Any]:
    _ensure_dir(path)
    if not os.path.exists(path):
        return {"version": 1, "senders": {}, "domains": {}, "events": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "senders": {}, "domains": {}, "events": []}

def _save_store(store: Dict[str, Any], path: str = DEFAULT_STORE_PATH) -> None:
    _ensure_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _get_domain(sender_email: str) -> str:
    s = (sender_email or "").lower().strip()
    if "@" not in s:
        return ""
    return s.split("@", 1)[1].strip()

def _record_feedback_db(*, user_id: str, email_id: str, sender_email: str, sender_domain: str, clicked: str, subject: str, snippet: str, meta: Dict[str, Any], ts: int) -> Dict[str, Any]:
    from app.db import connect
    conn = connect(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO user_email_feedback(
            user_id,email_id,sender_email,sender_domain,clicked,subject,snippet,meta,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (user_id, email_id, sender_email, sender_domain, clicked, subject or "", (snippet or "")[:300], json.dumps(meta or {}), ts),
    )
    conn.commit(); conn.close()
    return {
        "ok": True,
        "stored": {
            "ts": ts, "email_id": email_id, "sender_email": sender_email,
            "sender_domain": sender_domain, "clicked": clicked, "subject": subject or "",
            "snippet": (snippet or "")[:300], "meta": meta or {},
        },
        "storage": "postgresql_user_scoped",
    }

def _feedback_counts_db(user_id: str, sender_email: str, sender_domain: str) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    from app.db import connect
    conn = connect(); cur = conn.cursor()
    sender_rows = cur.execute(
        "SELECT clicked, COUNT(*) AS n, MAX(created_at) AS last_ts FROM user_email_feedback WHERE user_id=? AND sender_email=? GROUP BY clicked",
        (user_id, sender_email),
    ).fetchall()
    domain_rows = cur.execute(
        "SELECT clicked, COUNT(*) AS n, MAX(created_at) AS last_ts FROM user_email_feedback WHERE user_id=? AND sender_domain=? GROUP BY clicked",
        (user_id, sender_domain),
    ).fetchall() if sender_domain else []
    conn.close()

    def make(rows):
        if not rows:
            return None
        counts = {k: 0 for k in LABELS}; total = 0; last_ts = 0
        for r in rows:
            key = str(r["clicked"] or "").upper()
            if key in counts:
                n = int(r["n"] or 0); counts[key] += n; total += n
                last_ts = max(last_ts, int(r["last_ts"] or 0))
        return {"counts": counts, "total": total, "last_ts": last_ts}

    return make(sender_rows), make(domain_rows)

def _init_bucket(store: Dict[str, Any], bucket: str, key: str) -> Dict[str, Any]:
    store.setdefault(bucket, {})
    if key not in store[bucket]:
        store[bucket][key] = {"counts": {k: 0 for k in LABELS}, "total": 0, "last_ts": 0}
    else:
        c = store[bucket][key].get("counts", {})
        for k in LABELS:
            c.setdefault(k, 0)
        store[bucket][key]["counts"] = c
        store[bucket][key].setdefault("total", 0)
        store[bucket][key].setdefault("last_ts", 0)
    return store[bucket][key]

def record_feedback(
    *,
    email_id: str,
    sender_email: str,
    clicked: str,
    subject: str = "",
    snippet: str = "",
    meta: Optional[Dict[str, Any]] = None,
    ts: Optional[int] = None,
    path: str = DEFAULT_STORE_PATH,
    user_id: str = "",
) -> Dict[str, Any]:
    clicked = (clicked or "").upper().strip()
    if clicked not in LABELS:
        raise ValueError(f"clicked must be one of {LABELS}")

    sender_email = (sender_email or "").lower().strip()
    sender_domain = _get_domain(sender_email)

    t = int(ts or _now())

    if user_id:
        return _record_feedback_db(
            user_id=user_id, email_id=email_id, sender_email=sender_email, sender_domain=sender_domain,
            clicked=clicked, subject=subject, snippet=snippet, meta=meta or {}, ts=t,
        )

    # Legacy single-user fallback only. Team/public flows always provide user_id
    # and therefore use PostgreSQL above.
    store = _load_store(path)
    scoped = store

    if sender_email:
        row = _init_bucket(scoped, "senders", sender_email)
        row["counts"][clicked] += 1
        row["total"] += 1
        row["last_ts"] = t

    if sender_domain:
        row = _init_bucket(scoped, "domains", sender_domain)
        row["counts"][clicked] += 1
        row["total"] += 1
        row["last_ts"] = t

    ev = {
        "ts": t,
        "email_id": email_id,
        "sender_email": sender_email,
        "sender_domain": sender_domain,
        "clicked": clicked,
        "subject": subject or "",
        "snippet": (snippet or "")[:300],
        "meta": meta or {},
    }
    scoped.setdefault("events", [])
    scoped["events"].append(ev)
    if len(scoped["events"]) > 2000:
        scoped["events"] = scoped["events"][-2000:]

    _save_store(store, path)
    return {"ok": True, "stored": ev}

def _posterior_best(counts: Dict[str, int], alpha: float = 1.0) -> Tuple[str, float]:
    total = sum(int(counts.get(k, 0)) for k in LABELS)
    denom = total + alpha * len(LABELS)
    probs = {k: (counts.get(k, 0) + alpha) / denom for k in LABELS}
    best = max(probs.items(), key=lambda kv: kv[1])
    return best[0], float(best[1])

def predict_user_preference(sender_email: str, *, path: str = DEFAULT_STORE_PATH, user_id: str = "") -> Optional[Dict[str, Any]]:
    sender_email = (sender_email or "").lower().strip()
    if not sender_email:
        return None

    domain = _get_domain(sender_email)
    if user_id:
        sender_row, domain_row = _feedback_counts_db(user_id, sender_email, domain)
    else:
        store = _load_store(path)
        sender_row = store.get("senders", {}).get(sender_email)
        domain_row = store.get("domains", {}).get(domain) if domain else None

    # anti-misclick guards
    min_evidence_sender = 3
    min_evidence_domain = 5
    min_conf = 0.70

    candidates = []

    if sender_row and int(sender_row.get("total", 0)) >= min_evidence_sender:
        b, c = _posterior_best(sender_row.get("counts", {}))
        candidates.append(("sender", b, c, int(sender_row.get("total", 0))))

    if domain_row and int(domain_row.get("total", 0)) >= min_evidence_domain:
        b, c = _posterior_best(domain_row.get("counts", {}))
        candidates.append(("domain", b, c, int(domain_row.get("total", 0))))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[2], reverse=True)
    source, label, conf, total = candidates[0]
    if conf < min_conf:
        return None

    return {
        "user_category": label,
        "user_category_confidence": conf,
        "user_category_source": source,
        "user_category_evidence": total,
    }

def apply_user_override(
    priority: float,
    label: str,
    respond_recommended: bool,
    pref: Optional[Dict[str, Any]],
) -> Tuple[float, str, bool]:
    if not pref:
        return float(priority or 0.0), (label or "LOW").upper(), bool(respond_recommended)

    cat = (pref.get("user_category") or "").upper()
    conf = float(pref.get("user_category_confidence", 0.0))

    p = float(priority or 0.0)
    lab = (label or "LOW").upper()
    rr = bool(respond_recommended)

    if cat in ("SPAM", "PROMO"):
        p = max(0.0, p - (0.22 + 0.08 * conf))
        lab = "LOW"
        rr = False

    elif cat == "IMPORTANT":
        p = min(1.0, p + (0.10 + 0.06 * conf))
        if lab == "LOW":
            lab = "MEDIUM"
        if p >= 0.85:
            lab = "HIGH"
        rr = True

    elif cat == "LESS":
        p = max(0.0, p - (0.06 + 0.03 * conf))
        if lab == "HIGH":
            lab = "MEDIUM"

    return p, lab, rr