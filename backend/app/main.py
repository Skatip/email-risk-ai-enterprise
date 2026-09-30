from fastapi import FastAPI, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
import asyncio
import time
import threading
import os
import base64
from dotenv import load_dotenv

load_dotenv()

from app.db import init_db, kv_get, kv_set
from app.gmail_service import (fetch_full_thread, fetch_inbox_fast, fetch_email_body, fetch_gmail_attachment, create_reply_draft,
    list_inbox_message_ids, fetch_message_metadata_batch)
from app.calendar_service import free_busy
from app.time_grounding import extract_requested_time, extract_ics_time
from app.reply_agent import save_rag_example, load_reply_memories
from app.communication_brain.orchestrator import process_communication
from app.communication_brain.triage import triage_messages, analyze_message_semantics
from app.api.google_oauth import router as google_oauth_router
from app.api.mcp_tools import router as mcp_tools_router
from app.integration_store import init_integration_store
from app.inbox_persistence import (init_inbox_persistence, load_messages, save_metadata, save_semantics, touch_messages, load_recent_messages, ANALYSIS_VERSION)
from app.email_rag import init_email_rag, sync_email_rag, rag_status, answer_email_question
from app.obligation_service import init_obligations, upsert_from_followup, query_obligations
from app.reply_multi import generate_multi
from app.learning import record_feedback
from app.thread_summary_agent import summarize_thread
from app.compose_from_notes_agent import write_from_notes
from app.analytics_service import track_email_event, get_analytics_summary
from app.attachment_analysis import analyze_attachment_bytes
from app.risk_engine import compute_risk
from app.attachment_bundle import content_hash, get_cached_attachment, save_cached_attachment, aggregate_attachment_intelligence

try:
    from app.followup_service import (
        create_followup,
        list_followups,
        list_due_followups,
        update_followup_status,
        snooze_followup,
        suggest_followup_from_brain,
        dismiss_meeting_reminders_for_thread,
    )
except Exception:
    from app.followup_service import create_followup, list_followups, dismiss_meeting_reminders_for_thread
    list_due_followups = None
    update_followup_status = None
    snooze_followup = None
    suggest_followup_from_brain = None

app = FastAPI(title="Enterprise Communication Intelligence API", version="2.0.0")
app.include_router(google_oauth_router)
app.include_router(mcp_tools_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173").split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gmail filtering is handled inside gmail_service.py.
# It fetches Primary + Spam from the last 7 days and does not hide emails here.
def _effective_query(user_query: str) -> str:
    return (user_query or "").strip()


def _labels_text(item: Dict[str, Any]) -> str:
    labels = item.get("labelIds") or item.get("labels") or []
    return " ".join(str(x).lower() for x in labels)


# No keyword-based human/security/importance filter here. Gmail provides candidates;
# semantic triage decides which messages deserve the intelligent inbox.


def _is_scheduling_request(email: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    """Use Brain judgment plus factual calendar attachments; never keyword-classify meaning."""
    if bool((analysis or {}).get("meeting_related")):
        return True
    for att in (email.get("attachments") or []):
        filename = str(att.get("filename") or "").lower()
        mime = str(att.get("mimeType") or att.get("mime_type") or "").lower()
        if filename.endswith(".ics") or "text/calendar" in mime:
            return True
    return False


def _ground_followup_time(email: Dict[str, Any], follow: Dict[str, Any], scheduling: bool = False) -> Dict[str, Any]:
    """Prefer a deterministic time parsed from the email over an LLM-guessed timestamp."""
    grounded = extract_requested_time(email) if scheduling else None
    event_at = int((grounded or {}).get("event_at_unix") or 0)
    llm_remind = int((follow or {}).get("remind_at_unix") or 0)
    if event_at > 0:
        # Do not invent a universal "15 minutes before" reminder. A reminder time
        # must come from communication intelligence / explicit calendar evidence.
        remind_at = llm_remind if 0 < llm_remind <= event_at else 0
        return {
            "remind_at": remind_at,
            "event_at": event_at,
            "event_timezone": grounded.get("timezone", ""),
            "reminder_kind": "meeting",
            "requested_time": grounded,
        }
    return {
        "remind_at": llm_remind,
        "event_at": llm_remind,
        "event_timezone": "",
        "reminder_kind": "email",
        "requested_time": None,
    }


async def _persist_grounded_followup(email: Dict[str, Any], semantic: Dict[str, Any], provider: str, user_id: str) -> bool:
    """Persist three separate concepts correctly: meeting registry, reminder, follow-up.

    Meetings may create a timed reminder even when no conversational follow-up is
    required. Non-meeting follow-ups require explicit semantic evidence AND a
    grounded time; no synthetic now+1h deadlines are allowed.
    """
    if not user_id:
        return False
    follow = semantic.get("follow_up") or {}
    scheduling = _is_scheduling_request(email, semantic)
    timing = _ground_followup_time(email, follow, scheduling=scheduling)

    # Calendar MIME data is factual and takes precedence over prose/LLM timing.
    # Gmail may expose an ICS either by attachmentId or inline body.data.
    if scheduling:
        for att in (email.get("attachments") or []):
            filename = str(att.get("filename") or "").lower()
            mime = str(att.get("mimeType") or att.get("mime_type") or "").lower()
            if not (filename.endswith(".ics") or "text/calendar" in mime):
                continue
            data = b""
            inline = str(att.get("inline_data") or "")
            if inline:
                try:
                    data = base64.urlsafe_b64decode(inline + "=" * (-len(inline) % 4))
                except Exception:
                    data = b""
            if not data:
                aid = att.get("attachmentId") or att.get("attachment_id")
                if aid:
                    try:
                        data = await asyncio.to_thread(fetch_gmail_attachment, str(email.get("id")), str(aid), user_id)
                    except Exception as exc:
                        print(f"Calendar attachment fetch warning for {email.get('id')}: {exc}")
            parsed = extract_ics_time(data) if data else None
            if parsed:
                event_at = int(parsed.get("event_at_unix") or 0)
                timing = {
                    # Calendar time is factual; reminder timing is a separate
                    # judgment. Preserve a grounded Brain reminder if one exists
                    # rather than imposing a fixed lead time.
                    "remind_at": int(timing.get("remind_at") or 0),
                    "event_at": event_at,
                    "event_end_at": int(parsed.get("event_end_unix") or event_at),
                    "event_timezone": parsed.get("timezone") or "",
                    "reminder_kind": "meeting",
                    "requested_time": parsed,
                    "event_uid": parsed.get("event_uid") or "",
                    "cancelled": bool(parsed.get("cancelled")),
                    "calendar_sequence": int(parsed.get("calendar_sequence") or 0),
                }
                break

    # Security/authentication notices are alerts, not overdue commitments by
    # default. They remain visible through Security/Inbox intelligence.
    intent = str(semantic.get("intent") or "").upper()
    security_only = bool(semantic.get("security_event")) and not any(x in intent for x in ("PAYMENT", "DEADLINE", "MEETING", "CALENDAR", "APPOINTMENT"))

    if scheduling and int(timing.get("event_at") or 0) > 0:
        # Persist canonical meeting lifecycle independently from Follow-ups.
        await asyncio.to_thread(upsert_from_followup, user_id, email, timing, semantic, provider)
        # A meeting reminder is a reminder, not a Follow-up; it is stored in the
        # reminder table but filtered from the Follow-ups UI.
        if bool(timing.get("cancelled")):
            await asyncio.to_thread(dismiss_meeting_reminders_for_thread, user_id, str(email.get("threadId") or ""))
        elif int(timing.get("event_at") or 0) > int(time.time()) and int(timing.get("remind_at") or 0) > 0:
            await asyncio.to_thread(
                create_followup, email.get("id", ""), timing["remind_at"],
                follow.get("note") or f"Reminder for {email.get('subject') or 'meeting'}",
                email.get("threadId", ""), email.get("subject", ""), email.get("from", ""),
                provider, user_id, timing["event_at"], timing["event_timezone"], "meeting",
            )
        semantic["grounded_timing"] = timing
        return True

    if security_only or not follow.get("needed"):
        return False

    # A conversational follow-up may be unresolved without having a deadline. Keep
    # it in Follow-ups with remind_at=0 rather than inventing a time. Timed reminders
    # are created only when the Brain/context provides a grounded timestamp.
    await asyncio.to_thread(
        create_followup, email.get("id", ""), int(timing.get("remind_at") or 0),
        follow.get("note") or follow.get("reason") or "Follow up on this email",
        email.get("threadId", ""), email.get("subject", ""), email.get("from", ""),
        provider, user_id, timing["event_at"], timing["event_timezone"], "followup",
    )
    timing["reminder_kind"] = "followup"
    semantic["grounded_timing"] = timing
    await asyncio.to_thread(upsert_from_followup, user_id, email, timing, semantic, provider)
    return True



async def _background_enrich_actionable_emails(emails: List[Dict[str, Any]], provider: str, user_id: str) -> None:
    """Ingest recent Gmail messages deeply without requiring a dashboard click.

    Gmail's metadata format does not include MIME attachment structure, so an ICS
    meeting can be invisible until the message is fetched with format=full. This
    background pass fetches recent messages after the inbox response, persists the
    richer metadata, and only invokes deeper Brain analysis when the message has
    calendar evidence or the existing semantic result asks for temporal persistence.
    """
    if provider != "gmail" or not user_id:
        return
    sem = asyncio.Semaphore(max(1, min(int(os.getenv("BACKGROUND_EMAIL_CONCURRENCY", "3")), 6)))

    async def one(card: Dict[str, Any]):
        async with sem:
            try:
                full = await asyncio.to_thread(fetch_email_body, card.get("id"), user_id)
                # Persist full structural metadata (including ICS descriptors) so the
                # Meetings surface can reconcile independently of the inbox UI.
                await asyncio.to_thread(save_metadata, user_id, [full], "gmail")
                has_ics = any(
                    str(a.get("filename") or "").lower().endswith(".ics")
                    or "text/calendar" in str(a.get("mimeType") or a.get("mime_type") or "").lower()
                    for a in (full.get("attachments") or [])
                )
                existing = card.get("_semantic") or {}
                if not (has_ics or bool(existing.get("meeting_related")) or bool(existing.get("follow_up_needed"))):
                    return
                semantic = await asyncio.to_thread(analyze_message_semantics, full, existing, thread=[], attachment_context=[])
                if semantic.get("id"):
                    await asyncio.to_thread(save_semantics, user_id, [semantic], "gmail")
                await _persist_grounded_followup(full, semantic, provider, user_id)
            except Exception as exc:
                print(f"Background intelligence warning for {card.get('id')}: {exc}")

    await asyncio.sleep(0.35)
    # Newest first, but keep separate messages even when they share a thread so a
    # calendar cancellation/update can reconcile the original invitation by UID.
    await asyncio.gather(*(one(x) for x in (emails or [])[:12]), return_exceptions=True)


async def _background_sync_inbox_incremental(user_id: str, provider: str = "gmail", query: str = "") -> None:
    """Refresh Neon without blocking inbox rendering.

    The serving path reads the already-processed mailbox from Neon. This worker only
    discovers a bounded recent Gmail ID window and processes IDs that Neon does not
    already know. It deliberately does not re-fetch/re-analyze the whole mailbox.
    """
    if provider != "gmail" or not user_id:
        return
    try:
        scan_limit = max(20, min(int(os.getenv("BACKGROUND_SYNC_DISCOVERY_LIMIT", "40")), 80))
        discovered_ids = await asyncio.to_thread(
            list_inbox_message_ids, _effective_query(query), scan_limit, user_id
        )
        if not discovered_ids:
            return
        persisted = await asyncio.to_thread(load_messages, user_id, discovered_ids, "gmail")
        new_ids = [mid for mid in discovered_ids if mid not in persisted or not persisted[mid].get("metadata")]
        await asyncio.to_thread(touch_messages, user_id, discovered_ids, "gmail")
        if not new_ids:
            return

        # Metadata + one compact Brain pass only for genuinely new messages.
        fresh = await asyncio.to_thread(fetch_message_metadata_batch, new_ids, user_id)
        if not fresh:
            return
        await asyncio.to_thread(save_metadata, user_id, fresh, "gmail")
        triaged = await asyncio.to_thread(triage_messages, fresh)
        if triaged:
            await asyncio.to_thread(save_semantics, user_id, [x for x in triaged if x.get("id")], "gmail")
        triage_map = {str(x.get("id")): x for x in (triaged or []) if x.get("id")}

        # Full MIME fetch is restricted to NEW messages only. This is needed to read
        # factual ICS evidence that Gmail's metadata format omits; it is not a mailbox scan.
        deep_cards = [{**m, "_semantic": triage_map.get(str(m.get("id")), {})} for m in fresh]
        await _background_enrich_actionable_emails(deep_cards, "gmail", user_id)

        # New data should be visible on the next refresh immediately.
        with _ANALYZE_CACHE_LOCK:
            for key in list(_ANALYZE_CACHE):
                if f"|{user_id}|" in key:
                    _ANALYZE_CACHE.pop(key, None)
    except Exception as exc:
        print(f"Incremental Gmail sync warning: {exc}")


_ANALYZE_CACHE: Dict[str, Any] = {}
_ANALYZE_CACHE_LOCK = threading.Lock()
_ANALYZE_CACHE_TTL = int(os.getenv("INBOX_CACHE_TTL_SECONDS", "8"))


def _cache_get(key: str):
    now = time.time()
    with _ANALYZE_CACHE_LOCK:
        item = _ANALYZE_CACHE.get(key)
        if not item:
            return None
        exp, value = item
        if exp < now:
            _ANALYZE_CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value):
    with _ANALYZE_CACHE_LOCK:
        _ANALYZE_CACHE[key] = (time.time() + _ANALYZE_CACHE_TTL, value)


def _clear_cache():
    with _ANALYZE_CACHE_LOCK:
        _ANALYZE_CACHE.clear()

_ATTACHMENT_RESULT_CACHE: Dict[str, Any] = {}
_ATTACHMENT_RESULT_CACHE_LOCK = threading.Lock()
_ATTACHMENT_RESULT_CACHE_TTL = int(os.getenv("ATTACHMENT_RESULT_CACHE_TTL_SECONDS", "1800"))


def _attachment_cache_get(key: str):
    now = time.time()
    with _ATTACHMENT_RESULT_CACHE_LOCK:
        item = _ATTACHMENT_RESULT_CACHE.get(key)
        if not item:
            return None
        exp, value = item
        if exp < now:
            _ATTACHMENT_RESULT_CACHE.pop(key, None)
            return None
        return value


def _attachment_cache_set(key: str, value):
    with _ATTACHMENT_RESULT_CACHE_LOCK:
        _ATTACHMENT_RESULT_CACHE[key] = (time.time() + _ATTACHMENT_RESULT_CACHE_TTL, value)



async def _analyze_all_email_attachments(email: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Analyze every supported attachment in one email, cache by SHA-256, then aggregate the documents."""
    attachments = list(email.get("attachments") or [])[: int(os.getenv("MAX_ATTACHMENTS_PER_EMAIL", "8"))]
    results: List[Dict[str, Any]] = []
    for attachment in attachments:
        attachment_id = attachment.get("attachment_id")
        if not attachment_id:
            continue
        filename = attachment.get("filename") or "attachment"
        mime_type = attachment.get("mime_type") or ""
        data = await asyncio.to_thread(fetch_gmail_attachment, email.get("id"), attachment_id, user_id)
        sha256 = content_hash(data)
        cached = await asyncio.to_thread(get_cached_attachment, user_id, sha256)
        if cached:
            result = {**cached, "content_hash": sha256, "cache_hit": True}
        else:
            result = await asyncio.to_thread(
                analyze_attachment_bytes,
                filename,
                mime_type,
                data,
                email.get("sender_band", ""),
                email.get("source_folder", ""),
                email.get("subject", ""),
                email.get("from", ""),
                email.get("snippet", ""),
            )
            result = {**result, "content_hash": sha256, "cache_hit": False}
            await asyncio.to_thread(save_cached_attachment, user_id, sha256, filename, result)
        results.append(result)

    bundle = await asyncio.to_thread(aggregate_attachment_intelligence, results)
    return {"attachment_analysis": results, "attachment_bundle": bundle, "attachment_reply_context": bundle.get("reply_context", "")}


@app.on_event("startup")
def _startup():
    init_db()
    if kv_get("last_seen_ts") is None:
        kv_set("last_seen_ts", "0")
    init_integration_store()
    init_inbox_persistence()
    init_email_rag()
    init_obligations()


@app.get("/inbox")
async def inbox_fast(
    user_email: str = Query(default=""),
    query: str = Query(default=""),
    max_results: int = Query(default=12),
    bucket: str = Query(default="IMPORTANT"),
    provider: str = Query(default="gmail"),
    user_id: str = Query(default=""),
):
    """
    Intelligent inbox endpoint.
    Fetches a bounded Primary + Spam candidate pool, then uses one compact semantic
    triage call to rank direct human and important messages before returning cards.
    """
    cache_key = f"inbox|{user_id}|{provider}|{user_email}|{query}|{bucket}|{max_results}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        if provider == "outlook":
            raise HTTPException(
                status_code=501,
                detail="Outlook is intentionally disabled until Microsoft OAuth is configured; app-password login is not supported.",
            )
        else:
            # NEON-FIRST SERVING PATH: do not wait for Gmail or an LLM before rendering.
            # Pull enough already-processed rows to let the Brain-ranked bucket return
            # the requested count, then refresh Gmail independently in the background.
            serve_from_neon = True
            cached_rows = await asyncio.to_thread(
                load_recent_messages, user_id, "gmail", max(80, min(max_results * 8, 200))
            )
            raw = []
            persisted_semantics: Dict[str, Dict[str, Any]] = {}
            for row in cached_rows:
                clean = {k: v for k, v in row.items() if not str(k).startswith("_")}
                if clean.get("id"):
                    raw.append(clean)
                    persisted_semantics[str(clean.get("id"))] = row.get("_semantic") or {}
            all_recent_for_background = []

            # Sync is intentionally detached from the response. Existing cards stay
            # visible while only new Gmail IDs are discovered and processed.
            try:
                asyncio.create_task(_background_sync_inbox_incremental(user_id, provider, query))
            except Exception as bg_sync_err:
                print(f"Incremental sync scheduling warning: {bg_sync_err}")

            # Empty Neon is a first-run/bootstrap case only. Fetch a small window so a
            # new workspace is usable, but never perform the old 80-200 message scan.
            if not raw:
                discovered_ids = await asyncio.to_thread(
                    list_inbox_message_ids, _effective_query(query), max(20, min(max_results * 2, 30)), user_id
                )
                fresh = await asyncio.to_thread(fetch_message_metadata_batch, discovered_ids, user_id) if discovered_ids else []
                if fresh:
                    await asyncio.to_thread(save_metadata, user_id, fresh, "gmail")
                    triaged = await asyncio.to_thread(triage_messages, fresh)
                    if triaged:
                        await asyncio.to_thread(save_semantics, user_id, [x for x in triaged if x.get("id")], "gmail")
                    sem_map = {str(x.get("id")): x for x in (triaged or []) if x.get("id")}
                    raw = fresh
                    persisted_semantics.update(sem_map)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fast inbox fetch failed: {str(e)}")

    # De-duplicate by thread so one active conversation does not crowd out the inbox.
    candidates: List[Dict[str, Any]] = []
    seen_threads = set()
    for e in raw:
        thread_key = e.get("threadId") or e.get("id")
        if thread_key in seen_threads:
            continue
        seen_threads.add(thread_key)
        candidates.append(e)

    # Gmail folders are retrieval sources only. The Communication Brain decides
    # what deserves space in the intelligent inbox. One compact batched call keeps
    # token/cost usage bounded while preventing newsletters/job feeds from crowding
    # out direct human and important messages.
    triage_by_id: Dict[str, Dict[str, Any]] = dict(locals().get("persisted_semantics", {}))
    if provider == "gmail" and candidates:
        try:
            # Reuse persisted Communication Brain output when the analysis contract
            # is unchanged. This removes repeat LLM latency on every app launch.
            persisted_now = await asyncio.to_thread(load_messages, user_id, [x.get("id") for x in candidates], "gmail")
            to_triage = []
            for item in candidates:
                item_id = str(item.get("id"))
                if triage_by_id.get(item_id):
                    continue
                saved = persisted_now.get(item_id, {})
                semantic = saved.get("semantic") or {}
                if semantic:
                    triage_by_id[item_id] = semantic
                else:
                    to_triage.append(item)
            # Never make the user wait for semantic enrichment of already-cached
            # rows. Pending semantics can be repaired asynchronously; Focus still
            # returns the requested recent candidates instead of collapsing to 1-2.
            if locals().get("serve_from_neon"):
                to_triage = []
            if to_triage:
                triaged = await asyncio.to_thread(triage_messages, to_triage)
                new_semantics = [x for x in triaged if x.get("id")]
                triage_by_id.update({str(x.get("id")): x for x in new_semantics})
                await asyncio.to_thread(save_semantics, user_id, new_semantics, "gmail")
        except Exception as triage_err:
            print(f"Semantic inbox triage warning: {triage_err}")

    out: List[Dict[str, Any]] = []
    for e in candidates:
        semantic = triage_by_id.get(str(e.get("id")), {})
        priority = float(semantic.get("priority", 0.0) or 0.0)
        sender_type = semantic.get("sender_type") or "UNKNOWN"
        out.append({
            "id": e.get("id"),
            "threadId": e.get("threadId"),
            "from": e.get("from", ""),
            "subject": e.get("subject", ""),
            "snippet": e.get("snippet", ""),
            "body": "",
            "ts": e.get("ts", 0),
            "labelIds": e.get("labelIds") or e.get("labels") or [],
            "attachments": e.get("attachments", []),
            "has_attachments": bool(e.get("attachments", [])),
            "provider": provider,
            "priority": priority,
            "inbox_score": float(semantic.get("inbox_score", priority) or 0.0),
            "label": semantic.get("label") or "PENDING",
            "risk": float(semantic.get("risk", 0.0) or 0.0),
            "sender_band": (
                "HUMAN" if semantic.get("direct_human")
                else "AUTOMATED" if sender_type == "AUTOMATED"
                else "COMPANY" if sender_type == "COMPANY"
                else "PERSONAL" if sender_type == "PERSONAL"
                else "UNKNOWN"
            ),
            "sender_type": sender_type,
            "intent": semantic.get("intent") or "pending",
            "reason": semantic.get("reason") or "Awaiting deeper analysis.",
            "priority_reason": semantic.get("priority_reason") or "",
            "respond_recommended": bool(semantic.get("respond_recommended", False)),
            "reply_decision": semantic.get("reply_decision") or "NO_REPLY",
            "direct_human": bool(semantic.get("direct_human", False)),
            "requires_action": bool(semantic.get("requires_action", False)),
            "security_event": bool(semantic.get("security_event", False)),
            "security_reason": semantic.get("security_reason") or "",
            "triage_confidence": float(semantic.get("confidence", 0.0) or 0.0),
            "meeting_related": bool(semantic.get("meeting_related", False)),
            "follow_up_needed": bool(semantic.get("follow_up_needed", False)),
            "human_signals": {"sender_type": sender_type},
            "analysis_status": "triaged" if semantic else "pending",
            "source_folder": e.get("source_folder", ""),
            "bucket": semantic.get("bucket") or "INFORMATIONAL",
            "communication_type": semantic.get("communication_type") or "AUTOMATED",
            "email_type": semantic.get("email_type") or "UNCLASSIFIED",
            "relationship_type": semantic.get("relationship_type") or "UNKNOWN",
            "basic_classification": e.get("basic_classification", {}),
            "mail_scope": "SEMANTIC_PRIMARY_AND_SPAM_LAST_7_DAYS" if provider == "gmail" else "FAST_INBOX",
        })

    if triage_by_id:
        out.sort(key=lambda x: (float(x.get("inbox_score", 0.0)), float(x.get("priority", 0.0)), int(x.get("ts", 0))), reverse=True)
    else:
        out.sort(key=lambda x: int(x.get("ts", 0)), reverse=True)

    # Preserve the complete analyzed candidate set for background meeting/deadline
    # discovery. A meeting must not disappear from the Meetings registry merely
    # because the user is currently viewing another inbox bucket.
    background_candidates = []
    for item in all_recent_for_background:
        sem_saved = triage_by_id.get(str(item.get("id")), {})
        background_candidates.append({**item, "_semantic": sem_saved})

    requested_bucket = (bucket or "FOCUS").upper()
    if requested_bucket in {"FOCUS", "IMPORTANT"}:
        # Focus is the Brain's contextual attention ranking over recent Primary+Spam.
        # No sender/domain/keyword/priority threshold decides importance here.
        # Focus means the Brain's ranked answer to “what deserves attention now”.
        # Do not require a fixed semantic bucket; return the requested number of
        # highest-ranked recent Primary+Spam candidates.
        out.sort(key=lambda x: (float(x.get("inbox_score", 0.0)), int(x.get("ts", 0))), reverse=True)
    elif requested_bucket == "NEEDS_REPLY":
        out = [x for x in out if x.get("respond_recommended") or str(x.get("reply_decision") or "").upper() == "DRAFT_REPLY"]
    elif requested_bucket == "PEOPLE":
        out = [x for x in out if x.get("direct_human") or str(x.get("bucket") or "").upper() in {"CONVERSATIONAL", "FOLLOW_UP"}]
    elif requested_bucket == "WORK_CAREER":
        out = [x for x in out if str(x.get("bucket") or "").upper() in {"BUSINESS", "RECRUITING"}]
    elif requested_bucket == "MONEY_SECURITY":
        out = [x for x in out if str(x.get("bucket") or "").upper() in {"TRANSACTIONAL", "SECURITY"}]
    elif requested_bucket == "UPDATES":
        out = [x for x in out if str(x.get("bucket") or "").upper() in {"INFORMATIONAL", "JOB_FEED", "MARKETING", "SOCIAL", "AUTOMATED_LOW_VALUE"}]
    elif requested_bucket != "ALL":
        out = [x for x in out if str(x.get("bucket") or "").upper() == requested_bucket]

    out = out[:max_results]
    _cache_set(cache_key, out)
    return out


async def _reconcile_cached_meetings(user_id: str, limit: int = 180) -> None:
    """Repair the meeting registry from already-cached Gmail evidence.

    This runs only for the Meetings surface/low-priority background work. It does not
    block the inbox. Meeting candidates come from semantic intent or calendar evidence,
    not company-specific sender rules.
    """
    rows = await asyncio.to_thread(load_recent_messages, user_id, "gmail", limit)
    for card in rows:
        sem = card.get("_semantic") or {}
        attachments = card.get("attachments") or []
        has_ics = any(str(a.get("filename") or "").lower().endswith(".ics") or "text/calendar" in str(a.get("mimeType") or a.get("mime_type") or "").lower() for a in attachments)
        semantic_meeting = bool(sem.get("meeting_related"))
        if not (has_ics or semantic_meeting):
            continue
        timing = extract_requested_time(card)
        # ICS is authoritative when available. Fetch only tiny calendar attachments,
        # never all attachments and never all message bodies.
        if has_ics:
            for att in attachments:
                if not (str(att.get("filename") or "").lower().endswith(".ics") or "text/calendar" in str(att.get("mimeType") or att.get("mime_type") or "").lower()):
                    continue
                aid = att.get("attachmentId") or att.get("attachment_id")
                data = b""
                inline = str(att.get("inline_data") or "")
                if inline:
                    try:
                        data = base64.urlsafe_b64decode(inline + "=" * (-len(inline) % 4))
                    except Exception:
                        data = b""
                if not data and aid:
                    try:
                        data = await asyncio.to_thread(fetch_gmail_attachment, str(card.get("id")), str(aid), user_id)
                    except Exception as exc:
                        print(f"ICS meeting reconciliation warning for {card.get('id')}: {exc}")
                parsed = extract_ics_time(data) if data else None
                if parsed:
                    timing = parsed
                    break
        if not timing and semantic_meeting:
            try:
                full = await asyncio.to_thread(fetch_email_body, card.get("id"), user_id)
                timing = extract_requested_time({**card, **full})
            except Exception:
                timing = None
        if not timing or int(timing.get("event_at_unix") or 0) <= 0:
            continue
        normalized = {**sem, "meeting_related": True}
        grounded = {
            "event_at": int(timing["event_at_unix"]),
            "event_end_at": int(timing.get("event_end_unix") or timing["event_at_unix"]),
            # Reconciliation never invents a reminder lead. Meeting persistence and
            # reminder persistence are separate concerns.
            "remind_at": 0,
            "event_timezone": timing.get("timezone") or "",
            "reminder_kind": "meeting",
            "requested_time": timing,
            "event_uid": timing.get("event_uid") or "",
            "cancelled": bool(timing.get("cancelled")),
            "calendar_sequence": int(timing.get("calendar_sequence") or 0),
        }
        await asyncio.to_thread(upsert_from_followup, user_id, card, grounded, normalized, "gmail")
        # Keep reminder separate from meeting registry.
        if bool(grounded.get("cancelled")):
            await asyncio.to_thread(dismiss_meeting_reminders_for_thread, user_id, str(card.get("threadId") or ""))
        elif int(grounded.get("event_at") or 0) > int(time.time()) and int(grounded.get("remind_at") or 0) > 0:
            try:
                await asyncio.to_thread(create_followup, card.get("id", ""), grounded["remind_at"], f"Reminder for {card.get('subject') or 'meeting'}", card.get("threadId", ""), card.get("subject", ""), card.get("from", ""), "gmail", user_id, grounded["event_at"], grounded["event_timezone"], "meeting")
            except Exception as exc:
                print(f"Meeting reminder reconciliation warning for {card.get('id')}: {exc}")


@app.get("/meetings")
async def meetings(user_id: str = Query(default=""), limit: int = Query(default=100), refresh: bool = Query(default=True)):
    """Persistent meeting registry, independent from inbox pagination and follow-ups."""
    if not user_id:
        return []
    if refresh:
        try:
            await _reconcile_cached_meetings(user_id)
        except Exception as exc:
            print(f"Meeting registry reconciliation warning: {exc}")
    rows = await asyncio.to_thread(query_obligations, user_id, limit)
    meetings_only = [r for r in rows if str(r.get("kind") or "").lower() in {"meeting", "calendar", "appointment"}]
    # Multiple invitation/update emails can refer to one event. Show the event once.
    deduped, seen = [], set()
    for row in meetings_only:
        title_key = " ".join(str(row.get("title") or "").lower().split())
        sender_key = str(row.get("source_sender") or "").lower().strip()
        event_uid = str(row.get("event_uid") or "").strip()
        key = ("uid", event_uid) if event_uid else ("fallback", int(row.get("due_at") or 0), title_key, sender_key)
        if key in seen:
            continue
        seen.add(key); deduped.append(row)
    return deduped[:limit]


@app.post("/email/analyze")
async def email_analyze(payload: Dict[str, Any] = Body(...)):
    """Deep semantic analysis for one rendered email using the Communication Brain."""
    email = payload.get("email") or {}
    provider = payload.get("provider") or email.get("provider") or "gmail"
    user_id = payload.get("user_id", "")

    if not email:
        raise HTTPException(status_code=400, detail="email required")

    try:
        if provider == "gmail" and email.get("id") and not (email.get("body") or "").strip():
            try:
                full = await asyncio.to_thread(fetch_email_body, email.get("id"), user_id)
                email = {**email, **full}
            except Exception as body_err:
                print(f"Analyze body fetch warning: {body_err}")

        # Deep analysis must see the real conversation, not an isolated snippet.
        thread: List[Dict[str, Any]] = payload.get("thread") or []
        if provider == "gmail" and email.get("threadId") and user_id and not thread:
            try:
                thread = await asyncio.to_thread(fetch_full_thread, email.get("threadId"), user_id)
            except Exception as thread_err:
                print(f"Analyze thread fetch warning: {thread_err}")

        # Attachments are first-class context. Analyze all real attachments once and
        # reuse the SHA-256 cache. Provider-generated HTML body artifacts are filtered
        # in gmail_service before this point.
        attachment_result: Dict[str, Any] = {}
        attachment_context = payload.get("attachment_context") or email.get("attachment_analysis") or []
        if provider == "gmail" and user_id and email.get("attachments") and not attachment_context:
            try:
                attachment_result = await _analyze_all_email_attachments(email, user_id)
                attachment_context = attachment_result.get("attachment_analysis") or []
            except Exception as attachment_err:
                print(f"Analyze attachment warning: {attachment_err}")

        semantic = await asyncio.to_thread(
            analyze_message_semantics,
            email,
            payload.get("analysis") or email,
            thread=thread,
            attachment_context=attachment_context,
        )

        deterministic_risk = compute_risk(
            str(email.get("subject") or ""),
            str(email.get("body") or email.get("snippet") or ""),
            str(email.get("from") or ""),
            context=semantic,
        )
        item = {
            **email,
            **semantic,
            "provider": provider,
            "user_id": user_id,
            "analysis_status": "done",
            "source_folder": email.get("source_folder", ""),
            "attachments": email.get("attachments", []),
            "has_attachments": bool(email.get("attachments", [])),
            "human_signals": {
                "sender_type": semantic.get("sender_type", "UNKNOWN"),
                "direct_human": bool(semantic.get("direct_human", False)),
            },
            "risk_signals": deterministic_risk.signals,
            "risk_reasons": list(dict.fromkeys(
                deterministic_risk.reasons + ([semantic.get("security_reason")] if semantic.get("security_event") and semantic.get("security_reason") else [])
            )),
            "risk_urls": deterministic_risk.urls,
            "attachment_analysis": attachment_result.get("attachment_analysis") or attachment_context or email.get("attachment_analysis") or [],
            "attachment_bundle": attachment_result.get("attachment_bundle") or email.get("attachment_bundle") or {},
            "attachment_reply_context": attachment_result.get("attachment_reply_context") or email.get("attachment_reply_context") or "",
        }

        # Persist only a grounded reminder. For scheduling messages the concrete
        # time in the email wins over any model-generated timestamp.
        follow = semantic.get("follow_up") or {}
        try:
            if await _persist_grounded_followup(email, semantic, provider, user_id):
                item["followup_persisted"] = True
                item["grounded_timing"] = semantic.get("grounded_timing")
        except Exception as follow_err:
            print(f"Automatic follow-up warning: {follow_err}")

        item["ai_follow_up"] = follow
        item["commitments"] = semantic.get("commitments") or []

        try:
            track_email_event(item)
        except Exception as track_err:
            print(f"Analytics track error: {track_err}")

        return item
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email analysis failed: {str(e)}")


@app.get("/analyze")
async def analyze(
    user_email: str = Query(default=""),
    query: str = Query(default=""),
    max_results: int = Query(default=10),
    include_thread_context: bool = Query(default=False),
    include_reply: bool = Query(default=False),
    reply_top_n: int = Query(default=0),
    provider: str = Query(default="gmail"),
    user_id: str = Query(default=""),
):
    """Backward compatible endpoint. Now uses semantic inbox + per-email analysis."""
    base = await inbox_fast(user_email=user_email, query=query, max_results=max_results, provider=provider, user_id=user_id)
    analyzed = []
    for email in base:
        try:
            item = await email_analyze({"email": email, "provider": provider, "user_id": user_id})
        except Exception:
            item = email
        analyzed.append(item)
    return analyzed


@app.post("/reply/generate")
async def reply_generate(payload: Dict[str, Any] = Body(...)):
    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    force = bool(payload.get("force", False))
    user_id = payload.get("user_id", "")
    if not email:
        raise HTTPException(status_code=400, detail="email payload is required")
    try:
        provider = email.get("provider") or analysis.get("provider") or "gmail"
        if provider == "gmail" and not (email.get("body") or "").strip() and email.get("id"):
            try:
                full = await asyncio.to_thread(fetch_email_body, email.get("id"), user_id)
                email = {**email, **full}
            except Exception as body_err:
                print(f"Reply body fetch warning: {body_err}")

        thread = payload.get("thread") or []
        if provider == "gmail" and not thread and email.get("threadId") and user_id:
            try:
                thread = await asyncio.to_thread(fetch_full_thread, email.get("threadId"), user_id)
            except Exception as thread_err:
                print(f"Reply thread fetch warning: {thread_err}")

        attachment_context = payload.get("attachment_context") or analysis.get("attachment_analysis") or email.get("attachment_analysis") or []
        attachment_bundle = payload.get("attachment_bundle") or analysis.get("attachment_bundle") or email.get("attachment_bundle") or {}

        # If the email has attachments but no current intelligence, analyze every document now.
        # This keeps reply generation grounded in all documents in the message, not just the first file.
        if provider == "gmail" and user_id and email.get("attachments") and not attachment_context:
            try:
                bundle_result = await _analyze_all_email_attachments(email, user_id)
                attachment_context = bundle_result.get("attachment_analysis") or []
                attachment_bundle = bundle_result.get("attachment_bundle") or {}
                email = {**email, **bundle_result}
                analysis = {**analysis, **bundle_result}
            except Exception as attachment_err:
                print(f"Reply multi-attachment analysis warning: {attachment_err}")

        if attachment_context and not attachment_bundle:
            try:
                attachment_bundle = await asyncio.to_thread(aggregate_attachment_intelligence, list(attachment_context))
            except Exception as bundle_err:
                print(f"Attachment bundle aggregation warning: {bundle_err}")

        # The bundle is appended as one compact cross-document context object so the brain
        # can understand relationships/conflicts across multiple attachments.
        combined_attachment_context = list(attachment_context or [])
        if attachment_bundle:
            combined_attachment_context.append({
                "document_type": "attachment_bundle",
                "document_label": "Combined Attachment Intelligence",
                "summary": attachment_bundle.get("summary", ""),
                "key_details": attachment_bundle.get("key_facts", []),
                "action_items": attachment_bundle.get("action_items", []),
                "dates": attachment_bundle.get("deadlines", []),
                "reply_context": attachment_bundle.get("reply_context", ""),
                "priority_reason": attachment_bundle.get("priority_reason", ""),
                "conflicts": attachment_bundle.get("conflicts", []),
            })

        memories = payload.get("memories") or (load_reply_memories(user_id) if user_id else [])
        user_preferences = payload.get("user_preferences") or {}

        result = await asyncio.to_thread(
            process_communication,
            email,
            analysis,
            force=force,
            thread=thread,
            attachment_context=combined_attachment_context,
            memories=memories,
            user_preferences=user_preferences,
        )

        # Temporal reply guard: never draft future-attendance language for a meeting
        # whose grounded event time has already passed. The user may later choose a
        # specific post-meeting action (e.g. apologize/reschedule), but the default
        # reply path must not claim they will attend a past event.
        scheduling = _is_scheduling_request(email, {**analysis, **result})
        grounded_for_reply = extract_requested_time(email) if scheduling else None
        grounded_event_at = int((grounded_for_reply or {}).get("event_at_unix") or 0)
        attendance_confirmation = str(user_preferences.get("attendance_confirmation") or "").strip().lower()
        if scheduling and grounded_event_at and grounded_event_at < int(time.time()) and not attendance_confirmation:
            result["decision"] = "ASK_USER"
            result["reply"] = ""
            result["should_reply"] = False
            result["respond_recommended"] = False
            result["needs_user_input"] = True
            result["event_lifecycle"] = "past_unknown"
            result["clarification_question"] = "This meeting has already ended. Did you attend it, miss it, or is no further action needed?"
            result["reason"] = "The meeting is in the past, but attendance is unknown. Human confirmation is required before any post-meeting reply."

        # Deterministic scheduling safety guard. Even if the model prematurely drafts
        # an acceptance, a scheduling message cannot produce a reply until the user
        # explicitly confirms availability. We ground the requested time from the
        # actual email text and use Calendar only to report conflicts.
        availability_confirmation = str(user_preferences.get("availability_confirmation") or "").strip().lower()
        scheduling = _is_scheduling_request(email, {**analysis, **result})
        grounded_request = extract_requested_time(email) if scheduling else None
        if scheduling and not availability_confirmation and grounded_request and int(grounded_request.get("event_at_unix") or 0) >= int(time.time()):
            result["decision"] = "CHECK_CALENDAR"
            result["reply"] = ""
            result["should_reply"] = False
            result["respond_recommended"] = False
            result["tool_request"] = {
                "type": "calendar.check_availability",
                "time_min": grounded_request["time_min"],
                "time_max": grounded_request["time_max"],
            }
            result["requested_time"] = grounded_request

        # Scheduling chronology:
        # 1) read the calendar only, 2) ask the user, 3) draft only after explicit user input.
        # A free calendar is not permission to accept a meeting on the user's behalf.
        if result.get("decision") == "CHECK_CALENDAR" and user_id and not availability_confirmation:
            req = result.get("tool_request") or {}
            if req.get("time_min") and req.get("time_max"):
                try:
                    availability = await asyncio.to_thread(free_busy, user_id, req["time_min"], req["time_max"])
                    busy = list(availability.get("busy") or [])
                    result["decision"] = "ASK_USER"
                    result["reply"] = ""
                    result["should_reply"] = False
                    result["respond_recommended"] = False
                    result["needs_user_input"] = True
                    result["calendar_checked"] = True
                    result["calendar_availability"] = availability
                    result["requested_time"] = grounded_request or result.get("requested_time")
                    if busy:
                        result["clarification_question"] = "Your calendar shows a conflict during the requested time. Are you still available for this meeting?"
                    else:
                        result["clarification_question"] = "Your calendar looks free during the requested time. Are you actually available for this meeting?"
                except Exception as calendar_err:
                    result["decision"] = "ASK_USER"
                    result["reply"] = ""
                    result["should_reply"] = False
                    result["respond_recommended"] = False
                    result["needs_user_input"] = True
                    result["clarification_question"] = "I couldn't verify your calendar. Are you available for the requested meeting time?"
                    result["calendar_error"] = str(calendar_err)
        try:
            if await _persist_grounded_followup(email, result, provider, user_id):
                result["followup_persisted"] = True
        except Exception as follow_err:
            print(f"Reply follow-up warning: {follow_err}")
        result["attachments"] = email.get("attachments", [])
        result["attachment_analysis"] = attachment_context
        result["attachment_bundle"] = attachment_bundle
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reply generation failed: {str(e)}")


@app.post("/reply/multi")
async def multi_reply(payload: Dict[str, Any] = Body(...)):
    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    user_id = payload.get("user_id", "")
    if not email:
        raise HTTPException(status_code=400, detail="email payload is required")
    provider = email.get("provider") or analysis.get("provider") or "gmail"
    if provider == "gmail" and email.get("id") and not (email.get("body") or "").strip():
        try:
            full = await asyncio.to_thread(fetch_email_body, email.get("id"), user_id)
            email = {**email, **full}
        except Exception as body_err:
            print(f"Multi reply body fetch warning: {body_err}")
    thread = []
    if provider == "gmail" and email.get("threadId") and user_id:
        try:
            thread = await asyncio.to_thread(fetch_full_thread, email.get("threadId"), user_id)
        except Exception as thread_err:
            print(f"Multi reply thread fetch warning: {thread_err}")

    attachment_context = analysis.get("attachment_analysis") or email.get("attachment_analysis") or []
    attachment_bundle = analysis.get("attachment_bundle") or email.get("attachment_bundle") or {}
    if provider == "gmail" and user_id and email.get("attachments") and not attachment_context:
        try:
            bundle_result = await _analyze_all_email_attachments(email, user_id)
            attachment_context = bundle_result.get("attachment_analysis") or []
            attachment_bundle = bundle_result.get("attachment_bundle") or {}
        except Exception as attachment_err:
            print(f"Multi reply attachment warning: {attachment_err}")
    if attachment_context and not attachment_bundle:
        try:
            attachment_bundle = await asyncio.to_thread(aggregate_attachment_intelligence, list(attachment_context))
        except Exception:
            attachment_bundle = {}
    combined = list(attachment_context or [])
    if attachment_bundle:
        combined.append({
            "document_type": "attachment_bundle",
            "document_label": "Combined Attachment Intelligence",
            "summary": attachment_bundle.get("summary", ""),
            "key_details": attachment_bundle.get("key_facts", []),
            "action_items": attachment_bundle.get("action_items", []),
            "dates": attachment_bundle.get("deadlines", []),
            "reply_context": attachment_bundle.get("reply_context", ""),
            "conflicts": attachment_bundle.get("conflicts", []),
        })
    memories = load_reply_memories(user_id) if user_id else []
    return await asyncio.to_thread(generate_multi, email, analysis, thread=thread, attachment_context=combined, memories=memories)


@app.post("/reply/save_example")
def reply_save_example(payload: Dict[str, Any] = Body(...)):
    inbound = (payload.get("inbound") or "").strip()
    outbound = (payload.get("outbound") or "").strip()
    label = (payload.get("label") or "style").strip() or "style"
    if not inbound or not outbound:
        raise HTTPException(status_code=400, detail="inbound and outbound required")
    return save_rag_example(inbound, outbound, label=label, user_id=payload.get("user_id", ""))


@app.post("/feedback")
def feedback(payload: Dict[str, Any] = Body(...)):
    sender_email = (payload.get("sender_email") or "").strip()
    clicked = (payload.get("clicked") or "").strip().upper()
    if not sender_email:
        raise HTTPException(status_code=400, detail="sender_email is required")
    if not clicked:
        raise HTTPException(status_code=400, detail="clicked is required")
    result = record_feedback(
        email_id=(payload.get("email_id") or "").strip(),
        sender_email=sender_email,
        clicked=clicked,
        subject=payload.get("subject") or "",
        snippet=payload.get("snippet") or "",
        meta=payload.get("meta") or {},
        user_id=payload.get("user_id", ""),
    )
    _clear_cache()
    return result


@app.get("/thread/full")
async def thread_full(thread_id: str, provider: str = Query(default="gmail"), user_id: str = Query(default="")):
    if provider == "outlook":
        raise HTTPException(status_code=400, detail="Outlook full thread not added yet")
    return {"thread": await asyncio.to_thread(fetch_full_thread, thread_id, user_id)}


@app.post("/thread/summary")
async def thread_summary_api(payload: Dict[str, Any] = Body(...)):
    thread_id = payload.get("thread_id")
    provider = payload.get("provider", "gmail")
    provided_emails = payload.get("emails") or []
    if provider == "outlook":
        return await asyncio.to_thread(summarize_thread, provided_emails or [payload.get("email") or {}])
    if not thread_id:
        if provided_emails:
            return await asyncio.to_thread(summarize_thread, provided_emails)
        raise HTTPException(status_code=400, detail="thread_id required")
    emails = await asyncio.to_thread(fetch_full_thread, thread_id, payload.get("user_id", ""))
    return await asyncio.to_thread(summarize_thread, emails)


@app.post("/followups/create")
def followup_create(payload: Dict[str, Any] = Body(...)):
    return create_followup(
        email_id=payload.get("email_id"),
        thread_id=payload.get("thread_id", ""),
        remind_at=payload.get("remind_at"),
        note=payload.get("note", ""),
        subject=payload.get("subject", ""),
        sender=payload.get("sender", ""),
        provider=payload.get("provider", "gmail"),
        user_id=payload.get("user_id", ""),
        event_at=payload.get("event_at", 0),
        event_timezone=payload.get("event_timezone", ""),
        reminder_kind=payload.get("reminder_kind", "email"),
    )


@app.get("/followups")
def followups(user_id: str = Query(default=""), status: str = Query(default=""), limit: int = Query(default=100)):
    return list_followups(user_id=user_id, status=status or None, limit=limit)


@app.get("/followups/due")
def followups_due(user_id: str = Query(default=""), limit: int = Query(default=100)):
    if list_due_followups is None:
        return []
    return list_due_followups(user_id=user_id, mark_due=True, limit=limit)


@app.post("/followups/{followup_id}/status")
def followup_status(followup_id: int, payload: Dict[str, Any] = Body(...)):
    if update_followup_status is None:
        raise HTTPException(status_code=400, detail="Followup status update not available")
    return update_followup_status(followup_id, payload.get("status"), payload.get("user_id", ""))


@app.post("/followups/{followup_id}/snooze")
def followup_snooze(followup_id: int, payload: Dict[str, Any] = Body(default={})):
    if snooze_followup is None:
        raise HTTPException(status_code=400, detail="Followup snooze is not available")
    seconds = int(payload.get("seconds") or payload.get("delay_seconds") or 3600)
    return snooze_followup(followup_id, payload.get("user_id", ""), seconds=seconds)


@app.post("/followups/suggest")
def followup_suggest(payload: Dict[str, Any] = Body(...)):
    if suggest_followup_from_brain is None:
        raise HTTPException(status_code=400, detail="Followup suggestion is not available")
    return suggest_followup_from_brain(payload.get("brain_result") or payload.get("analysis") or {})


@app.post("/compose/from-notes")
def compose_notes(payload: Dict[str, Any] = Body(...)):
    return write_from_notes(payload.get("notes"), payload.get("tone", "professional"))


@app.get("/analytics")
def analytics(days: int = Query(default=14), user_id: str = Query(default="")):
    try:
        return get_analytics_summary(days=days, user_id=user_id)
    except TypeError:
        return get_analytics_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics failed: {str(e)}")


@app.post("/attachments/analyze")
async def attachment_analyze(payload: Dict[str, Any] = Body(...)):
    provider = payload.get("provider", "gmail")
    message_id = payload.get("message_id") or payload.get("email_id")
    attachment = payload.get("attachment") or {}
    user_id = payload.get("user_id", "")

    if provider != "gmail":
        raise HTTPException(status_code=400, detail="Attachment analysis currently supports Gmail only.")
    if not message_id or not user_id:
        raise HTTPException(status_code=400, detail="message_id and user_id are required")

    attachment_id = attachment.get("attachment_id") or payload.get("attachment_id")
    filename = attachment.get("filename") or payload.get("filename") or "attachment"
    mime_type = attachment.get("mime_type") or payload.get("mime_type") or ""
    if not attachment_id:
        raise HTTPException(status_code=400, detail="attachment_id is required")

    try:
        data = await asyncio.to_thread(fetch_gmail_attachment, message_id, attachment_id, user_id)
        sha256 = content_hash(data)
        cached = await asyncio.to_thread(get_cached_attachment, user_id, sha256)
        if cached is not None:
            return {**cached, "content_hash": sha256, "cache_hit": True}

        result = await asyncio.to_thread(
            analyze_attachment_bytes,
            filename,
            mime_type,
            data,
            payload.get("sender_band", ""),
            payload.get("source_folder", ""),
            payload.get("email_subject", ""),
            payload.get("email_sender", ""),
            payload.get("email_snippet", ""),
        )
        result = {**result, "content_hash": sha256, "cache_hit": False}
        await asyncio.to_thread(save_cached_attachment, user_id, sha256, filename, result)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Attachment analysis failed: {str(e)}")


@app.post("/attachments/analyze-all")
async def attachments_analyze_all(payload: Dict[str, Any] = Body(...)):
    """Analyze every attachment in an email and build one cross-document intelligence bundle."""
    email = payload.get("email") or {}
    user_id = payload.get("user_id", "")
    if not email or not email.get("id"):
        raise HTTPException(status_code=400, detail="email with id is required")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if (email.get("provider") or "gmail") != "gmail":
        raise HTTPException(status_code=400, detail="Multi-attachment analysis currently supports Gmail only")
    try:
        return await _analyze_all_email_attachments(email, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Multi-attachment analysis failed: {str(e)}")


@app.post("/gmail/reply-draft")
async def gmail_reply_draft(payload: Dict[str, Any] = Body(...)):
    """User-approved action: create a Gmail draft in the SAME original thread."""
    user_id = payload.get("user_id", "")
    thread_id = payload.get("thread_id", "")
    message_id = payload.get("message_id", "")
    reply_text = payload.get("reply_text", "")
    if not all((user_id, thread_id, message_id, str(reply_text).strip())):
        raise HTTPException(status_code=400, detail="user_id, thread_id, message_id and reply_text are required")
    try:
        return await asyncio.to_thread(create_reply_draft, user_id, thread_id, message_id, reply_text)
    except Exception as e:
        detail = str(e)
        if "insufficient" in detail.lower() or "scope" in detail.lower():
            detail += " Reconnect Google so Email-AI receives gmail.compose permission."
        raise HTTPException(status_code=500, detail=f"Gmail draft creation failed: {detail}")



@app.get("/rag/status")
async def email_rag_status(user_id: str = Query(default="")):
    if not user_id: raise HTTPException(status_code=400, detail="user_id is required")
    return await asyncio.to_thread(rag_status, user_id)


@app.post("/rag/sync")
async def email_rag_sync(payload: Dict[str, Any] = Body(...)):
    user_id = str(payload.get("user_id") or "")
    if not user_id: raise HTTPException(status_code=400, detail="user_id is required")
    max_messages = max(1, min(int(payload.get("max_messages") or 500), 5000))
    query = str(payload.get("query") or "in:anywhere")
    return await asyncio.to_thread(sync_email_rag, user_id, max_messages, query)


@app.post("/rag/ask")
async def email_rag_ask(payload: Dict[str, Any] = Body(...)):
    user_id = str(payload.get("user_id") or "")
    question = str(payload.get("question") or "").strip()
    if not user_id or not question: raise HTTPException(status_code=400, detail="user_id and question are required")
    user_timezone = str(payload.get("user_timezone") or "UTC")
    return await asyncio.to_thread(answer_email_question, user_id, question, user_timezone)

@app.get("/health")
def health():
    return {"status": "ok", "mode": "hosted_enterprise", "ai_provider": "openai", "database": "postgresql", "oauth": True, "mcp_ready": True, "bounded_loops": True}


@app.get("/")
def root():
    return {"message": "AI Email Backend running", "mode": "fast_inbox_async_analysis"}
