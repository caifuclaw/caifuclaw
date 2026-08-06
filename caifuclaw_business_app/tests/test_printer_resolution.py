from app import task_runner
from app.printer_identity import PrinterIdentity, printer_fingerprint


def test_printer_resolution_prefers_online_exact_name():
    resolved = task_runner._resolve_printer_identity(
        "WanChen_QR_586_2",
        [
            PrinterIdentity(name="WanChen_QR_586_3", system="windows", driver_name="WanChen", port_name="USB002", online=True),
            PrinterIdentity(name="WanChen_QR_586_2", system="windows", driver_name="WanChen", port_name="USB001", online=True),
        ],
    )

    assert resolved.resolved_name == "WanChen_QR_586_2"


def test_printer_resolution_uses_fingerprint_when_saved_name_is_offline():
    current = PrinterIdentity(name="WanChen_QR_586_3", system="windows", driver_name="WanChen", port_name="USB001", online=True)
    saved_fingerprint = printer_fingerprint(
        PrinterIdentity(name="WanChen_QR_586_2", system="windows", driver_name="WanChen", port_name="USB001")
    )

    resolved = task_runner._resolve_printer_identity(
        "WanChen_QR_586_2",
        [
            PrinterIdentity(name="WanChen_QR_586_2", system="windows", driver_name="WanChen", port_name="USB001", online=False),
            current,
        ],
        fingerprint=saved_fingerprint,
    )

    assert resolved.resolved_name == "WanChen_QR_586_3"
    assert resolved.online is True


def test_printer_resolution_stops_when_fingerprint_is_ambiguous():
    saved_fingerprint = printer_fingerprint(
        PrinterIdentity(name="WanChen_QR_586_2", system="windows", driver_name="WanChen", port_name="USB001")
    )

    resolved = task_runner._resolve_printer_identity(
        "WanChen_QR_586_2",
        [
            PrinterIdentity(name="WanChen_QR_586_3", system="windows", driver_name="WanChen", port_name="USB001", online=True),
            PrinterIdentity(name="WanChen_QR_586_4", system="windows", driver_name="WanChen", port_name="USB001", online=True),
        ],
        fingerprint=saved_fingerprint,
    )

    assert resolved.ambiguous is True
    assert resolved.resolved_name == "WanChen_QR_586_2"


def test_printer_resolution_does_not_fallback_by_name_when_fingerprint_misses():
    saved_fingerprint = printer_fingerprint(
        PrinterIdentity(name="WanChen_QR_586_2", system="windows", driver_name="WanChen", port_name="USB001")
    )

    resolved = task_runner._resolve_printer_identity(
        "WanChen_QR_586_2",
        [
            PrinterIdentity(name="WanChen_QR_586_3", system="windows", driver_name="OtherDriver", port_name="USB999", online=True),
        ],
        fingerprint=saved_fingerprint,
    )

    assert resolved.ambiguous is False
    assert resolved.exists is False
    assert resolved.resolved_name == "WanChen_QR_586_2"
