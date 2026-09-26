from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

from app.utils import clamp01


@dataclass
class RiskResult:
    risk_score: float
    signals: List[str]
    reasons: List[str]
    urls: List[Dict[str, str]]


_LINK_RE = re.compile(r"https?://[^\s<>()\]\[\"']+", re.I)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})", re.I)
_ASK_CRED = re.compile(r"\b(password|verify account|login|log in|sign in|confirm identity|otp|2fa|code|reset your account|validate your account)\b", re.I)
_URGENT = re.compile(r"\b(urgent|immediately|asap|act now|last chance|final warning|account will be closed|within 24 hours|today only)\b", re.I)
_MONEY = re.compile(r"\b(wire|gift card|bitcoin|crypto|payment|refund|invoice|overdue|bank|payroll|direct deposit|transfer)\b", re.I)
_ATTACHMENT = re.compile(r"\b(attachment|attached|invoice attached|open the file|download the file|enable macros|macro|zip file|password protected)\b", re.I)

# Exposed secrets are a sensitivity/security issue even when the sender is legitimate.
_SECRET_PATTERNS = [
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I)),
    ("generic_secret", re.compile(r"(?i)\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|secret[_ -]?key)\b\s*[:=]\s*[\"']?[A-Za-z0-9_./+\-=]{16,}")),
]
_SHORTENER_DOMAINS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rebrand.ly", "shorturl.at"}
_SUSPICIOUS_TLDS = {"zip", "mov", "click", "top", "xyz", "tk", "ml", "ga", "cf", "gq"}
_BRAND_WORDS = {"google", "gmail", "microsoft", "office", "outlook", "apple", "icloud", "paypal", "amazon", "facebook", "meta", "instagram", "bank", "chase", "wellsfargo"}


def _domain_from_sender(sender: str = "") -> str:
    m = _EMAIL_RE.search(sender or "")
    return (m.group(1).lower() if m else "").strip()


def _host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower().strip(".")
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _root_domain(host: str) -> str:
    parts = [p for p in (host or "").split(".") if p]
    if len(parts) < 2:
        return host or ""
    return ".".join(parts[-2:])


def _looks_like_ip(host: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host or ""))


def _brand_impersonation(host: str, sender_domain: str) -> Optional[str]:
    h = host.lower()
    sender_domain = sender_domain.lower()
    for brand in _BRAND_WORDS:
        if brand in h and brand not in sender_domain and not h.endswith(f"{brand}.com"):
            return brand
    return None


def compute_risk(subject: str, body: str, sender: str = "") -> RiskResult:
    text = f"{subject or ''}\n{body or ''}".strip()
    low = text.lower()
    score = 0.0
    signals: List[str] = []
    reasons: List[str] = []
    urls_out: List[Dict[str, str]] = []

    sender_domain = _domain_from_sender(sender)
    links = _LINK_RE.findall(text)

    exposed = [name for name, pattern in _SECRET_PATTERNS if pattern.search(text)]
    if exposed:
        # Do not echo the secret itself into logs/UI. Report only the type.
        score = max(score, 0.90)
        signals.append("exposed_secret")
        signals.extend(f"secret:{name}" for name in exposed)
        reasons.append("Sensitive credential or API secret appears to be exposed in the email content.")

    if links:
        score += 0.12
        signals.append("has_link")
        reasons.append("Email contains one or more links.")

    for url in links[:10]:
        host = _host(url)
        root = _root_domain(host)
        finding = "normal"

        if root in _SHORTENER_DOMAINS:
            score += 0.22
            signals.append("short_link")
            reasons.append(f"Shortened link detected: {host}")
            finding = "shortened_link"

        if _looks_like_ip(host):
            score += 0.25
            signals.append("ip_address_link")
            reasons.append("Link uses an IP address instead of a normal domain.")
            finding = "ip_address_link"

        if host and sender_domain and _root_domain(host) != _root_domain(sender_domain):
            score += 0.10
            signals.append("domain_mismatch")
            reasons.append(f"Link domain does not match sender domain: {host}")
            finding = "domain_mismatch"

        tld = host.split(".")[-1] if "." in host else ""
        if tld in _SUSPICIOUS_TLDS:
            score += 0.15
            signals.append("suspicious_tld")
            reasons.append(f"Suspicious link ending detected: .{tld}")
            finding = "suspicious_tld"

        brand = _brand_impersonation(host, sender_domain)
        if brand:
            score += 0.22
            signals.append("brand_impersonation")
            reasons.append(f"Possible {brand} impersonation in link domain: {host}")
            finding = "brand_impersonation"

        urls_out.append({"url": url, "host": host, "finding": finding})

    if _ASK_CRED.search(low):
        score += 0.30
        signals.append("credential_language")
        reasons.append("Email asks for login, password, OTP, or account verification.")

    if _URGENT.search(low):
        score += 0.16
        signals.append("urgency_language")
        reasons.append("Email uses urgency or pressure language.")

    if _MONEY.search(low):
        score += 0.14
        signals.append("money_language")
        reasons.append("Email discusses payment, invoice, refund, bank, or money movement.")

    if _ATTACHMENT.search(low):
        score += 0.13
        signals.append("attachment_language")
        reasons.append("Email references attachments, downloads, or files.")

    if "enable macros" in low or ".zip" in low or "password protected" in low:
        score += 0.25
        signals.append("high_risk_attachment_language")
        reasons.append("Attachment language looks risky, such as macros, ZIP, or password protected files.")

    if not reasons:
        reasons.append("No major phishing or fraud signals detected.")

    # Deduplicate while preserving order
    signals = list(dict.fromkeys(signals))
    reasons = list(dict.fromkeys(reasons))

    return RiskResult(
        risk_score=clamp01(score),
        signals=signals,
        reasons=reasons,
        urls=urls_out,
    )
