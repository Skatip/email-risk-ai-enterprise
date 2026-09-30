from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_triage_does_not_convert_priority_to_labels_with_thresholds():
    source = (ROOT / "backend/app/communication_brain/triage.py").read_text()
    assert "priority >= 0.72" not in source
    assert "priority >= 0.40" not in source
    assert "_calibrate_priority" not in source


def test_background_workflow_uses_communication_brain_not_legacy_priority_engine():
    source = (ROOT / "backend/app/ai_workflows.py").read_text()
    assert "priority_engine" not in source
    assert "analyze_message_semantics" in source


def test_no_fixed_meeting_reminder_lead_in_main_flow():
    source = (ROOT / "backend/app/main.py").read_text()
    assert "MEETING_REMINDER_LEAD_SECONDS" not in source
