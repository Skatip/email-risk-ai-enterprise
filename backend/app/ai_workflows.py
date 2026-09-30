from typing import Any, Dict


def analyze_email_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy/background entry point routed through the same Communication Brain.

    There must not be a second keyword/score-based semantic engine for async jobs;
    otherwise the dashboard and background persistence can disagree about meaning.
    """
    from app.gmail_service import fetch_email_body
    from app.communication_brain.triage import analyze_message_semantics
    from app.analytics_service import track_email_event

    email = payload.get("email") or {}
    provider = payload.get("provider") or email.get("provider") or "gmail"
    user_id = payload.get("user_id") or email.get("user_id") or ""
    if not email:
        raise ValueError("email required")

    if provider == "gmail" and email.get("id") and not (email.get("body") or "").strip():
        try:
            full = fetch_email_body(email.get("id"), user_id)
            email = {**email, **full}
        except Exception as body_err:
            print(f"Analyze body fetch warning: {body_err}")

    semantic = analyze_message_semantics(
        email,
        payload.get("analysis") or {},
        thread=payload.get("thread") or [],
        attachment_context=payload.get("attachment_context") or email.get("attachment_analysis") or [],
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
    }
    try:
        track_email_event(item)
    except Exception as track_err:
        print(f"Analytics track error: {track_err}")
    return item


def reply_generate_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_email_body
    from app.reply_agent import draft_reply

    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    force = bool(payload.get("force", False))
    user_id = payload.get("user_id") or email.get("user_id") or ""
    if not email:
        raise ValueError("email payload is required")

    if (email.get("provider") or analysis.get("provider") or "gmail") == "gmail":
        if not (email.get("body") or "").strip() and email.get("id"):
            try:
                full = fetch_email_body(email.get("id"), user_id)
                email = {**email, **full}
            except Exception as body_err:
                print(f"Reply body fetch warning: {body_err}")

    return draft_reply(email, analysis, force)


def multi_reply_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.reply_multi import generate_multi

    email = payload.get("email") or {}
    analysis = payload.get("analysis") or {}
    if not email:
        raise ValueError("email payload is required")
    return generate_multi(email, analysis)


def thread_summary_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_full_thread
    from app.thread_summary_agent import summarize_thread

    thread_id = payload.get("thread_id")
    provider = payload.get("provider", "gmail")
    provided_emails = payload.get("emails") or []

    if provider == "outlook":
        return summarize_thread(provided_emails or [payload.get("email") or {}])

    if not thread_id:
        if provided_emails:
            return summarize_thread(provided_emails)
        raise ValueError("thread_id required")

    emails = fetch_full_thread(thread_id)
    return summarize_thread(emails)


def attachment_analyze_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.gmail_service import fetch_gmail_attachment
    from app.attachment_analysis import analyze_attachment_bytes

    provider = payload.get("provider", "gmail")
    message_id = payload.get("message_id") or payload.get("email_id")
    attachment = payload.get("attachment") or {}

    if provider != "gmail":
        raise ValueError("Attachment analysis currently supports Gmail only.")
    if not message_id:
        raise ValueError("message_id is required")

    attachment_id = attachment.get("attachment_id") or payload.get("attachment_id")
    filename = attachment.get("filename") or payload.get("filename") or "attachment"
    mime_type = attachment.get("mime_type") or payload.get("mime_type") or ""

    if not attachment_id:
        raise ValueError("attachment_id is required")

    data = fetch_gmail_attachment(message_id, attachment_id, payload.get("user_id", ""))
    return analyze_attachment_bytes(
        filename,
        mime_type,
        data,
        payload.get("sender_band", ""),
        payload.get("source_folder", ""),
        payload.get("email_subject", ""),
        payload.get("email_sender", ""),
        payload.get("email_snippet", ""),
    )


def compose_notes_workflow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from app.compose_from_notes_agent import write_from_notes

    return write_from_notes(payload.get("notes"), payload.get("tone", "professional"))


def check_due_followups_workflow(payload: Dict[str, Any] | None = None):
    try:
        from app.followup_service import list_due_followups
        return list_due_followups(user_id=(payload or {}).get("user_id", ""), mark_due=True, limit=int((payload or {}).get("limit", 100)))
    except Exception as e:
        return {"ok": False, "error": str(e)}
