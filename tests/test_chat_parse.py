"""Date extraction for tariff replies (no network needed)."""

from backend.app.chat import _extract_dates


def test_extracts_iso_date_range():
    assert _extract_dates("Side 2026-10-05 to 2026-10-11") == (
        "2026-10-05",
        "2026-10-11",
    )


def test_returns_none_without_two_dates():
    assert _extract_dates("Side someday") is None
    assert _extract_dates("Side 2026-10-05") is None
