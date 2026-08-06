from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pypdf import PdfWriter

from app.label_tracking import clean_tracking_number
from scripts import sync_ozon_tracking_fallback as script


def _pdf_bytes(text: str = "") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=220, height=120)
    if text:
        # pypdf cannot add text to a blank page without reportlab; tests that need
        # positive extraction monkeypatch PdfReader instead.
        page[script.__name__] = text  # harmless non-rendered metadata-like value
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_split_values_dedupes_comma_separated_values():
    assert script._split_values(["100001,100002", "100001", "", " 100002 "]) == ["100001", "100002"]


def test_live_update_candidate_requires_awaiting_registration_without_tracking():
    update = SimpleNamespace(
        platform_status="awaiting_registration",
        shipment_tracking_number="",
        raw_payload={"status": "awaiting_registration", "substatus": "posting_awaiting_registration", "tracking_number": ""},
    )

    assert script._live_update_is_fallback_candidate(update) == (True, "")


def test_live_update_candidate_skips_when_tracking_is_available():
    update = SimpleNamespace(
        platform_status="awaiting_registration",
        shipment_tracking_number="DEMO-TRACKING-0026",
        raw_payload={"status": "awaiting_registration", "substatus": "posting_awaiting_registration"},
    )

    assert script._live_update_is_fallback_candidate(update) == (False, "tracking_already_available")


def test_wait_window_elapsed_uses_last_logistics_sync_time():
    now = datetime(2026, 7, 6, 1, 0, tzinfo=timezone.utc)
    stale = SimpleNamespace(logistics_last_synced_at=datetime(2026, 7, 6, 0, 0))
    recent = SimpleNamespace(logistics_last_synced_at=datetime(2026, 7, 6, 0, 45))

    assert script._wait_window_elapsed(stale, 30, now=now) == (True, "")
    ok, reason = script._wait_window_elapsed(recent, 30, now=now)
    assert ok is False
    assert reason.startswith("wait_not_elapsed:")


def test_label_text_contains_posting_with_mocked_pdf_reader(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "OZON GLOBAL\n52656278-0083-1 C\nXY Standard Small"

    class FakeReader:
        def __init__(self, _buffer):
            self.pages = [FakePage()]

    monkeypatch.setitem(__import__("sys").modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    assert script._label_text_contains_posting(b"%PDF fake", "52656278-0083-1") is True
    assert script._label_text_contains_posting(b"%PDF fake", "OTHER") is False


def test_build_summary_counts_actions_and_reasons():
    args = SimpleNamespace(
        dry_run=False,
        status="待处理",
        account_id=[],
        shop=[],
        order=[],
        limit=0,
        min_wait_minutes=30,
        verify_label_text=True,
        show_orders=10,
    )
    rows = [
        {"action": "applied", "reason": "applied"},
        {"action": "skipped", "reason": "status_not_returned"},
        {"action": "skipped", "reason": "status_not_returned"},
    ]

    summary = script._build_summary(
        args=args,
        started_at=datetime.now(timezone.utc),
        selected_count=3,
        rows=rows,
    )

    assert summary["selected_orders"] == 3
    assert summary["applied_orders"] == 1
    assert summary["skipped_orders"] == 2
    assert summary["reason_counts"] == {"applied": 1, "status_not_returned": 2}


def test_ozon_fallback_marker_allows_pending_posting_tracking():
    payload = {
        "posting_number": "50000000-0001-1",
        "status": "awaiting_registration",
        "substatus": "posting_awaiting_registration",
    }

    assert clean_tracking_number("50000000-0001-1", payload, "ozon") == ""

    payload["ozon_tracking_fallback"] = {
        "tracking_number": "50000000-0001-1",
        "source": "ozon_tracking_fallback",
    }

    assert clean_tracking_number("50000000-0001-1", payload, "ozon") == "50000000-0001-1"
