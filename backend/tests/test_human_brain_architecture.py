from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_triage_does_not_convert_priority_to_labels_with_thresholds():
    source = (ROOT / "backend/app/communication_brain/triage.py").read_text(encoding="utf-8")
    assert "priority >= 0.72" not in source
    assert "priority >= 0.40" not in source
    assert "_calibrate_priority" not in source


def test_background_workflow_uses_communication_brain_not_legacy_priority_engine():
    source = (ROOT / "backend/app/ai_workflows.py").read_text(encoding="utf-8")
    assert "priority_engine" not in source
    assert "analyze_message_semantics" in source


def test_no_fixed_meeting_reminder_lead_in_main_flow():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "MEETING_REMINDER_LEAD_SECONDS" not in source


def test_focus_routes_low_value_brain_buckets_out_of_dashboard():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert 'low_value_feed_buckets = {"JOB_FEED", "MARKETING", "SOCIAL", "AUTOMATED_LOW_VALUE"}' in source
    assert 'sender ==' not in source[source.find("low_value_feed_buckets"):source.find("low_value_feed_buckets") + 500]


def test_reply_lifecycle_prefers_ics_end_time():
    source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "_ground_calendar_time_for_reply" in source
    assert "grounded_event_end < int(time.time())" in source

def test_attachment_analysis_does_not_mutate_message_priority():
    source = (ROOT / "frontend/src/components/EmailCard.jsx").read_text(encoding="utf-8")
    assert "priority: patchedPriority" not in source
    assert "priority: Math.min(1, Number(item?.priority || 0) + boost)" not in source
