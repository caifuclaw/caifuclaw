import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PrinterIdentity:
    name: str
    system: str = ""
    device_uri: str = ""
    driver_name: str = ""
    port_name: str = ""
    status: str = ""
    online: bool | None = None


def normalize_printer_name(value: str) -> str:
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def strip_printer_copy_suffix(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    patterns = (
        r"\s*\((?:copy|副本|拷贝)\s*\d+\)\s*$",
        r"\s*（(?:copy|副本|拷贝)\s*\d+）\s*$",
        r"[_-]\d{1,2}\s*$",
    )
    for pattern in patterns:
        stripped = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        if stripped != text and stripped:
            return stripped
    return text


def printer_base_name_key(value: str) -> str:
    current = (value or "").strip()
    while current:
        stripped = strip_printer_copy_suffix(current)
        if stripped == current:
            break
        current = stripped
    return normalize_printer_name(current)


def printer_fingerprint(identity: PrinterIdentity) -> str:
    system = (identity.system or "").strip().lower()
    device_uri = (identity.device_uri or "").strip().lower()
    driver_name = (identity.driver_name or "").strip().lower()
    port_name = (identity.port_name or "").strip().lower()
    base_name = printer_base_name_key(identity.name)
    if device_uri:
        parts = ["device", system, device_uri]
    elif driver_name:
        parts = ["driver", system, driver_name, base_name]
    elif port_name:
        parts = ["port", system, port_name, base_name]
    else:
        parts = ["name", system, base_name]
    payload = "|".join((part or "").strip().lower() for part in parts)
    if not payload.strip("|"):
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
