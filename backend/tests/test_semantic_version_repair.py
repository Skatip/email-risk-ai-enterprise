from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_analysis_contract_version_is_current():
    source = (ROOT / "backend/app/inbox_persistence.py").read_text(encoding="utf-8")
    assert "semantic-v4-unified-brain" in source


def test_background_sync_repairs_stale_semantics_without_sender_rules():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert 'persisted[mid].get("analysis_version") != ANALYSIS_VERSION' in source
    assert "BACKGROUND_SEMANTIC_REPAIR_LIMIT" in source
    assert "stale_cards" in source
    assert "triage_messages, stale_cards" in source


def test_explicit_no_reply_is_not_rendered_as_check_reply():
    source = (ROOT / "frontend/src/components/EmailCard.jsx").read_text(encoding="utf-8")
    assert 'if (!isFinal && ["NO_REPLY"' not in source
    assert 'if (!shouldOfferReply(item)) return "No reply needed";' in source
