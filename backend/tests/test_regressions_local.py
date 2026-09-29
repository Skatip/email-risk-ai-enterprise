from datetime import datetime, timezone
from app.time_grounding import extract_requested_time, extract_ics_time
from app.inbox_policy import focus_eligible as _focus_eligible, is_meeting_candidate as _is_meeting_candidate


def test_explicit_meeting_date_not_email_received_date():
    email = {"subject": "Meeting Sep 28, 2026, 10:00 PM EDT", "ts": 1790000000}
    got = extract_requested_time(email)
    assert got
    dt = datetime.fromtimestamp(got["event_at_unix"], tz=timezone.utc)
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 9, 29, 2)


def test_ics_timezone_is_authoritative():
    raw = b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART;TZID=America/New_York:20260928T160000\r\nDTEND;TZID=America/New_York:20260928T163000\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    got = extract_ics_time(raw)
    assert got and got["timezone"] == "America/New_York"
    assert got["event_end_unix"] - got["event_at_unix"] == 1800


def test_schedule_intent_is_meeting_candidate():
    assert _is_meeting_candidate({"subject":"Practice session"}, {"intent":"SCHEDULE"})


def test_subject_meeting_invitation_is_candidate_even_generic_intent():
    assert _is_meeting_candidate({"subject":"Invitation to Join Meeting — Sep 28, 2026, 10:00 PM EDT"}, {"intent":"REQUEST"})


def test_low_email_never_occupies_focus():
    item = {"bucket":"RECRUITING", "label":"LOW", "inbox_score":.9, "direct_human":True}
    assert not _focus_eligible(item)


def test_high_action_email_qualifies_focus():
    item = {"bucket":"BUSINESS", "label":"HIGH", "inbox_score":.4, "requires_action":True}
    assert _focus_eligible(item)
