from app.time_grounding import extract_ics_time


def test_cancelled_ics_preserves_uid_and_end_time():
    ics = """BEGIN:VCALENDAR\r\nMETHOD:CANCEL\r\nBEGIN:VEVENT\r\nUID:practice-sandeep-20260929\r\nSEQUENCE:2\r\nDTSTART;TZID=America/New_York:20260929T120000\r\nDTEND;TZID=America/New_York:20260929T123000\r\nSTATUS:CANCELLED\r\nSUMMARY:Practice session for Sandeep\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"""
    result = extract_ics_time(ics)
    assert result is not None
    assert result["event_uid"] == "practice-sandeep-20260929"
    assert result["cancelled"] is True
    assert result["calendar_sequence"] == 2
    assert result["event_end_unix"] - result["event_at_unix"] == 1800


def test_normal_ics_is_not_cancelled():
    ics = """BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:nous-20260929\r\nDTSTART;TZID=America/New_York:20260929T220000\r\nDTEND;TZID=America/New_York:20260929T223000\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"""
    result = extract_ics_time(ics)
    assert result is not None
    assert result["event_uid"] == "nous-20260929"
    assert result["cancelled"] is False
    assert result["event_end_unix"] - result["event_at_unix"] == 1800
