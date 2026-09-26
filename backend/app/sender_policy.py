from dataclasses import dataclass
from app.db import get_sender
from app.utils import is_probably_bulk

@dataclass
class SenderPolicyResult:
    sender_band: str  # VIP | TRUSTED | PLATFORM | BULK | UNKNOWN | BLOCKED
    sender_boost: float
    reason: str

def sender_policy(sender_email: str, sender_name: str, subject: str) -> SenderPolicyResult:
    s = (sender_email or "").lower().strip()
    row = get_sender(s)

    # User overrides
    if row and int(row.get("blocked", 0)) == 1:
        return SenderPolicyResult("BLOCKED", -0.40, "user_blocked")

    if row and int(row.get("vip", 0)) == 1:
        return SenderPolicyResult("VIP", 0.35, "user_vip")

    # Learned trusted
    if row and int(row.get("total_count", 0)) >= 5:
        avg = float(row.get("avg_priority", 0.0))
        high = int(row.get("high_count", 0))
        if high >= 3 and avg >= 0.70:
            return SenderPolicyResult("TRUSTED", 0.18, "learned_trusted_sender")

    # Bulk senders
    if is_probably_bulk(sender_email, sender_name, subject):
        return SenderPolicyResult("BULK", -0.20, "bulk_sender_heuristic")

    return SenderPolicyResult("UNKNOWN", 0.0, "no_sender_history")