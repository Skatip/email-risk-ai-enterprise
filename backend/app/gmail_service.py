import base64
import os
import re
import time
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import settings
from app.attachment_analysis import classify_attachment, attachment_risk
from app.integration_store import get_connection

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"]

# User requirement: show Gmail messages from Primary and Spam only, within 1 week.
# We intentionally do NOT use -unsubscribe or broad sender blocking because that was hiding real emails.
DAYS_BACK = 7
PRIMARY_QUERY = f"in:inbox category:primary newer_than:{DAYS_BACK}d"
PRIMARY_FALLBACK_QUERY = f"in:inbox newer_than:{DAYS_BACK}d"
SPAM_QUERY = f"in:spam newer_than:{DAYS_BACK}d"

NOISE_CATEGORY_LABELS = {
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_FORUMS",
}

# Updates often contains bills, HR, school, and interview messages, so do not block it here.
# We classify it later as BILL / WORK / PROMOTIONAL instead of hiding it.
PERSONAL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "aol.com", "live.com", "msn.com", "proton.me", "protonmail.com",
}

# Semantic message meaning is intentionally NOT encoded as keyword lists here.
# Gmail service is transport/retrieval only; Communication Brain owns meaning,
# relationship, priority, security, reply/no-reply, and action decisions.



def _ensure_dir_for_file(file_path: str) -> None:
    d = os.path.dirname(file_path)
    if d:
        os.makedirs(d, exist_ok=True)


def gmail_service(user_id: str = ""):
    if not user_id:
        raise RuntimeError("Authenticated user context is required. Connect Gmail through Google OAuth.")
    stored = get_connection(user_id, "google")
    if not stored:
        raise RuntimeError("Gmail is not connected for this user")
    data = stored["credentials"]
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes") or SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _headers(payload: Dict[str, Any]) -> Dict[str, str]:
    return {
        h.get("name", "").lower(): h.get("value", "")
        for h in (payload.get("headers", []) or [])
    }


def _decode_body(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return ""


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    try:
        soup = BeautifulSoup(value, "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        text = soup.get_text("\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", value).strip()


def _get_plain_text(payload: Dict[str, Any]) -> str:
    """Extract the real message body, including HTML-only emails.

    Many recruiting, university, banking, and notification emails are HTML-only.
    Returning only text/plain caused the Communication Brain to see a Gmail snippet
    and describe complete emails as 'partial'.
    """
    plain_parts: List[str] = []
    html_parts: List[str] = []

    def walk(p: Dict[str, Any]):
        if not p:
            return
        mime = str(p.get("mimeType", "") or "").lower()
        body = p.get("body", {}) or {}
        data = body.get("data")
        filename = str(p.get("filename") or "").strip().lower()

        # Body MIME parts can have a filename in malformed/provider-generated mail.
        # They are still message content, not user documents.
        if data and mime == "text/plain":
            decoded = _decode_body(data)
            if decoded.strip():
                plain_parts.append(decoded)
        elif data and mime == "text/html":
            decoded = _decode_body(data)
            converted = _html_to_text(decoded)
            if converted.strip():
                html_parts.append(converted)

        for child in (p.get("parts", []) or []):
            walk(child)

    walk(payload or {})
    chosen = plain_parts if any(x.strip() for x in plain_parts) else html_parts
    text = "\n\n".join(x.strip() for x in chosen if x.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_email(sender: str) -> str:
    sender = sender or ""
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).strip().lower()
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", sender, flags=re.I)
    return match.group(0).lower() if match else sender.lower()


def _domain(sender: str) -> str:
    email = _extract_email(sender)
    return email.split("@")[-1].lower() if "@" in email else ""


def _is_primary_like(label_ids: List[str]) -> bool:
    labels = set(label_ids or [])
    if "SPAM" in labels:
        return True
    if "INBOX" not in labels:
        return False
    if labels.intersection(NOISE_CATEGORY_LABELS):
        return False
    return True


def classify_email(email: Dict[str, Any]) -> Dict[str, Any]:
    """Attach only transport/source metadata. Semantic classification happens in the Communication Brain."""
    labels = set(email.get("labelIds") or [])
    sender = email.get("from", "") or ""
    domain = _domain(sender)
    source_folder = "spam" if "SPAM" in labels else "primary"

    email["source_folder"] = source_folder
    email["email_type"] = "UNCLASSIFIED"
    email["relationship_type"] = "UNKNOWN"
    email["basic_classification"] = {
        "source_folder": source_folder,
        "domain": domain,
        "semantic_classification": "pending",
    }
    return email



def _extract_attachments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []

    def walk(p: Dict[str, Any]):
        if not p:
            return

        filename = p.get("filename") or ""
        body = p.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        mime_type = p.get("mimeType", "") or ""
        size = int(body.get("size", 0) or 0)

        if filename and attachment_id:
            low_name = filename.strip().lower()
            low_mime = mime_type.strip().lower()
            # Do not surface provider-generated copies of the email body as documents.
            # This fixes items such as `this_message_in_html.html` being analyzed as a
            # fake "General Document" attachment.
            body_artifact = (
                low_mime in {"text/html", "application/xhtml+xml"}
                or low_name.endswith((".html", ".htm"))
                or low_name in {"this_message_in_html.html", "message.html", "email.html"}
            )
            if not body_artifact:
                file_type = classify_attachment(filename, mime_type)
                risk = attachment_risk(filename, mime_type)
                attachments.append({
                    "filename": filename,
                    "mime_type": mime_type,
                    "file_type": file_type,
                    "attachment_id": attachment_id,
                    "size": size,
                    "risk_level": risk.get("risk_level", "low"),
                    "risk_score": risk.get("risk_score", 0.05),
                    "risk_reasons": risk.get("risk_reasons", []),
                })

        for child in (p.get("parts", []) or []):
            walk(child)

    walk(payload or {})
    return attachments


def _msg_to_email(msg: Dict[str, Any], include_body: bool = False) -> Dict[str, Any]:
    payload = msg.get("payload", {}) or {}
    headers = _headers(payload)
    attachments = _extract_attachments(payload)

    email = {
        "id": msg.get("id"),
        "threadId": msg.get("threadId"),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "message_id_header": headers.get("message-id", ""),
        "in_reply_to": headers.get("in-reply-to", ""),
        "references": headers.get("references", ""),
        "snippet": msg.get("snippet", "") or "",
        "body": _get_plain_text(payload) if include_body else "",
        "thread_context": "",
        "ts": int(msg.get("internalDate", "0") or 0) // 1000,
        "labelIds": msg.get("labelIds", []) or [],
        "attachments": attachments,
        "has_attachments": bool(attachments),
    }
    return classify_email(email)


def _append_user_query(base_query: str, user_query: str) -> str:
    q = (user_query or "").strip()
    if not q:
        return base_query
    return f"{base_query} {q}".strip()


def _list_message_ids(query: str, max_results: int, include_spam_trash: bool = False, user_id: str = "") -> List[str]:
    svc = gmail_service(user_id)
    resp = (
        svc.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=max_results,
            includeSpamTrash=include_spam_trash,
        )
        .execute()
    )
    return [m["id"] for m in (resp.get("messages", []) or [])]


def _primary_and_spam_ids(user_query: str = "", scan_limit: int = 80, user_id: str = "") -> List[str]:
    # Try true Gmail Primary first.
    ids = _list_message_ids(_append_user_query(PRIMARY_QUERY, user_query), scan_limit, False, user_id)

    # Fallback: some accounts/API responses don't return category:primary reliably.
    # In fallback, fetch inbox and keep primary-like labels after metadata/body fetch.
    if not ids:
        ids = _list_message_ids(_append_user_query(PRIMARY_FALLBACK_QUERY, user_query), scan_limit, False, user_id)

    spam_ids = _list_message_ids(_append_user_query(SPAM_QUERY, user_query), scan_limit, True, user_id)

    out: List[str] = []
    seen = set()
    for mid in ids + spam_ids:
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def fetch_inbox_fast(
    query: str = "",
    max_results: int = 10,
    scan_limit: int = 80,
    user_id: str = "",
) -> List[Dict[str, Any]]:
    """Fetch inbox metadata with Gmail HTTP batching.

    The previous implementation made one network round trip per message, which was
    the dominant first-load cost on Render. Gmail supports batched metadata gets;
    one bounded batch preserves the same message data while drastically reducing
    request overhead. If batching is unavailable, fall back to the original path.
    """
    svc = gmail_service(user_id)
    ids = _primary_and_spam_ids(query, max(scan_limit, max_results * 5), user_id)
    # We may need to inspect extra IDs because category filtering happens after fetch,
    # but keep the batch bounded for predictable latency and quota usage.
    fetch_ids = ids[: max(max_results * 3, max_results)]
    messages: Dict[str, Dict[str, Any]] = {}

    def _callback(request_id, response, exception):
        if exception is None and response:
            messages[str(request_id)] = response

    try:
        batch = svc.new_batch_http_request(callback=_callback)
        for message_id in fetch_ids:
            req = svc.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"],
            )
            batch.add(req, request_id=str(message_id))
        if fetch_ids:
            batch.execute()
    except Exception as batch_err:
        print(f"Gmail metadata batch warning: {batch_err}; falling back to sequential fetch")
        messages = {}
        for message_id in fetch_ids:
            try:
                messages[str(message_id)] = (
                    svc.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=["From", "To", "Subject", "Date"],
                    )
                    .execute()
                )
            except Exception as item_err:
                print(f"Gmail metadata fetch warning for {message_id}: {item_err}")

    results: List[Dict[str, Any]] = []
    # Reconstruct in Gmail list order so batching never changes inbox ordering.
    for message_id in fetch_ids:
        msg = messages.get(str(message_id))
        if not msg:
            continue
        email = _msg_to_email(msg, include_body=False)
        if not _is_primary_like(email.get("labelIds", [])):
            continue
        results.append(email)
        if len(results) >= max_results:
            break

    return results


def fetch_email_body(message_id: str, user_id: str = "") -> Dict[str, Any]:
    svc = gmail_service(user_id)
    msg = (
        svc.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    return _msg_to_email(msg, include_body=True)


def fetch_emails(
    query: str = "",
    max_results: int = 20,
    include_thread_context: bool = True,
    fast: bool = False,
    user_id: str = "",
) -> List[Dict[str, Any]]:
    if fast:
        return fetch_inbox_fast(
            query=query,
            max_results=max_results,
            scan_limit=max(max_results * 5, 80),
            user_id=user_id,
        )

    ids = _primary_and_spam_ids(query, max(max_results * 5, 80), user_id)
    results: List[Dict[str, Any]] = []

    for message_id in ids:
        full = fetch_email_body(message_id, user_id)

        if not _is_primary_like(full.get("labelIds", [])):
            continue

        thread_text = ""
        thread_id = full.get("threadId")

        if include_thread_context and thread_id:
            try:
                th = (
                    gmail_service(user_id)
                    .users()
                    .threads()
                    .get(userId="me", id=thread_id, format="metadata")
                    .execute()
                )

                ctx_chunks = []
                for tm in (th.get("messages", []) or [])[-4:]:
                    th_headers = _headers(tm.get("payload", {}) or {})
                    ctx_chunks.append(
                        "FROM: "
                        + th_headers.get("from", "")
                        + "\nSUBJECT: "
                        + th_headers.get("subject", "")
                        + "\nSNIPPET: "
                        + tm.get("snippet", "")
                    )

                thread_text = "\n---\n".join(ctx_chunks).strip()
            except Exception:
                thread_text = ""

        full["thread_context"] = thread_text
        results.append(classify_email(full))

        if len(results) >= max_results:
            break

    return results


def fetch_new_emails(after_unix_ts: int, max_results: int = 20) -> List[Dict[str, Any]]:
    emails = fetch_emails(
        query="",
        max_results=max_results,
        include_thread_context=True,
    )
    return [e for e in emails if int(e.get("ts", 0)) > int(after_unix_ts)]


def fetch_full_thread(thread_id: str, user_id: str = ""):
    svc = gmail_service(user_id)
    th = (
        svc.users()
        .threads()
        .get(userId="me", id=thread_id, format="full")
        .execute()
    )

    results = []
    for msg in th.get("messages", []) or []:
        results.append(_msg_to_email(msg, include_body=True))

    results.sort(key=lambda x: x.get("ts", 0))
    return results



def fetch_gmail_attachment(message_id: str, attachment_id: str, user_id: str = "") -> bytes:
    svc = gmail_service(user_id)
    att = (
        svc.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute()
    )
    data = att.get("data", "")
    if not data:
        return b""
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def _encode_mime_message(message) -> str:
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def create_reply_draft(
    user_id: str,
    thread_id: str,
    source_message_id: str,
    reply_text: str,
) -> Dict[str, Any]:
    """Create a Gmail draft that stays inside the original conversation thread.

    This is intentionally a DRAFT operation, not send. User approval remains required.
    """
    if not user_id:
        raise ValueError("user_id is required")
    if not thread_id or not source_message_id:
        raise ValueError("thread_id and source_message_id are required")
    if not (reply_text or "").strip():
        raise ValueError("reply_text is required")

    from email.message import EmailMessage

    svc = gmail_service(user_id)
    source = svc.users().messages().get(userId="me", id=source_message_id, format="metadata", metadataHeaders=["From", "To", "Cc", "Subject", "Message-ID", "References"]).execute()
    headers = _headers(source.get("payload", {}) or {})

    original_from = headers.get("from", "").strip()
    original_subject = headers.get("subject", "").strip()
    original_message_id = headers.get("message-id", "").strip()
    references = headers.get("references", "").strip()

    if not original_from:
        raise ValueError("Original sender address could not be determined")

    message = EmailMessage()
    message["To"] = original_from
    message["Subject"] = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
    if original_message_id:
        message["In-Reply-To"] = original_message_id
        message["References"] = (references + " " + original_message_id).strip()
    message.set_content((reply_text or "").strip())

    draft = svc.users().drafts().create(
        userId="me",
        body={
            "message": {
                "raw": _encode_mime_message(message),
                "threadId": thread_id,
            }
        },
    ).execute()

    return {
        "status": "draft_created",
        "draft_id": draft.get("id"),
        "message_id": (draft.get("message") or {}).get("id"),
        "thread_id": (draft.get("message") or {}).get("threadId") or thread_id,
    }
