from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_unavailable_triage_is_explicitly_marked_and_rejected():
    source = (ROOT / "backend/app/communication_brain/triage.py").read_text(encoding="utf-8")
    assert '"semantic_status": "unavailable"' in source
    assert "def is_usable_triage" in source
    assert '"PENDING"' in source and '"UNCLASSIFIED"' in source


def test_background_repair_includes_poisoned_same_version_fallbacks():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert 'or not is_usable_triage(persisted[mid].get("semantic") or {})' in source
    assert '[x for x in repaired if is_usable_triage(x)]' in source


def test_inbox_does_not_treat_unavailable_cached_semantics_as_brain_output():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "if is_usable_triage(saved_semantic):" in source
    assert "if is_usable_triage(semantic):" in source
