import asyncio
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, asc, case, exists, func, or_, select
from sqlalchemy.orm import Session

from common.wecom_robot import WeComRobotClient

try:
    import fitz
    import win32con
    import win32print
    import win32ui
    from PIL import Image, ImageWin
except Exception:
    fitz = None
    win32con = None
    win32print = None
    win32ui = None
    Image = None
    ImageWin = None

from .database import SessionLocal
from .bsi_sdms import BSI_CARRIER_CODE, BsiDraftGroupResult, process_bsi_drafts
from .label_storage import save_label_pdf
from .label_tracking import clean_tracking_number
from .email_service import EmailAttachment, get_email_setting, parse_recipients, send_email, send_final_failure_email
from .order_operation_logs import (
    ORDER_LOG_SYSTEM_SOURCE,
    SYSTEM_OPERATOR,
    add_order_operation_log,
    add_order_operation_logs,
)
from .pdf_tools import merge_pdf_parts, orient_pdf_bytes
from .chinese_label_pdf import (
    ChineseLabelRow,
    generate_chinese_label_pdf,
    resolve_chinese_label_deadline,
)
from .order_types import (
    joom_offline_shipping_target_status,
    order_has_bsi_draft,
    order_is_joom_fbj_warehouse,
    order_is_joom_offline_shipping,
    order_is_logistics_label_exempt,
    order_is_overseas_warehouse,
)
from .print_options import (
    PRINT_ORIENTATION_AUTO,
    PRINT_ORIENTATION_LANDSCAPE,
    PRINT_ORIENTATION_PORTRAIT,
    PRINT_PLATFORM_CHINESE_LABEL,
    label_orientation_for_platform,
    label_size_mm_for_platform,
    normalize_print_orientation,
)
from .printer_identity import (
    PrinterIdentity,
    normalize_printer_name,
    printer_base_name_key,
    printer_fingerprint,
)
from .models import (
    Order,
    OrderItem,
    OrderOperationLog,
    PlatformAccount,
    PlatformPrintSetting,
    ScheduledTask,
    ScheduledTaskRun,
    ScheduledTaskRunOrder,
    ScheduledTaskRunStep,
    Shipment,
)
from .product_matching import mapping_choice_for_order_item
from .product_models import Product, PurchaseOrder, PurchaseOrderSource
from .order_follow_up_export import enqueue_order_follow_up_export
from .purchase_order_notification import enqueue_purchase_order_wecom_notification
from .logistics_rules import (
    load_enabled_logistics_rules,
    order_matches_logistics_carrier_rule,
    split_logistics_rule_eligible_orders,
)
from .sync_engine import refresh_order_logistics_for_rows, submit_platform_shipments_and_refresh_logistics
from .wecom_service import load_wecom_robot_settings_from_db


ORDER_STATUS_PENDING = "待处理"
ORDER_STATUS_WAITING_PRINT = "待打印"
ORDER_STATUS_WAITING_PURCHASE = "待采购"
ORDER_STATUS_PICKING = "配货中"
ORDER_STATUS_SHIPPED = "已发货"

logger = logging.getLogger(__name__)

TASK_TYPE_AUTO_ORDER_PIPELINE = "auto_order_pipeline"
PRINT_DOCUMENT_TYPE_LABEL = "label"

STEP_SYNC_ORDERS = "sync_orders"
STEP_MOVE_TO_PRINTING = "move_to_printing"
STEP_SYNC_LOGISTICS = "sync_logistics"
STEP_CREATE_BSI_DRAFT = "create_bsi_draft"
STEP_QUEUE_JOOM_FBJ_FOLLOW_UP_EXPORT = "queue_joom_fbj_follow_up_export"
STEP_SKIP_OVERSEAS_WAREHOUSE = "skip_overseas_warehouse"
STEP_SKIP_LOGISTICS_LABEL_EXEMPT = "skip_logistics_label_exempt"
STEP_HANDLE_JOOM_OFFLINE_SHIPPING = "handle_joom_offline_shipping"
STEP_GENERATE_PDF = "generate_pdf"
STEP_MONITOR_PRINTER_STATUS = "monitor_printer_status"
STEP_SUBMIT_PRINT = "submit_print"
STEP_GENERATE_PURCHASE_ORDER = "generate_purchase_order"
STEP_MOVE_TO_PICKING = "move_to_picking"
STEP_MARK_SHIPPED = "mark_shipped"
STEP_LOGISTICS_READY_WAIT = "logistics_ready_wait"
STEP_NOTIFY_LOGISTICS_TIMEOUT = "notify_logistics_timeout"
STEP_FILTER_PURCHASE_ORDERS = "filter_purchase_orders"
STEP_MARK_DELIVERED_WITHOUT_LABEL_SHIPPED = "mark_delivered_without_label_shipped"

LOCAL_TIME_OFFSET = timedelta(hours=8)
DEFAULT_LOGISTICS_READY_TIMEOUT_SECONDS = 10 * 60
DEFAULT_LOGISTICS_READY_POLL_SECONDS = 30
TASK_TIMEOUT_COMPLETION_BUFFER_SECONDS = 60
STALE_RUNNING_TASK_BUFFER_SECONDS = 60
LOGISTICS_STALE_NOTIFY_AFTER = timedelta(hours=24)
POST_PRINT_MONITOR_KEY = "post_print_monitor"
POST_PRINT_MONITOR_DURATION = timedelta(minutes=15)
POST_PRINT_MONITOR_INTERVAL_SECONDS = 60
POST_PRINT_MONITOR_MAX_RECOVERY_ATTEMPTS = 3

ADOBE_READER_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Adobe\Reader 11.0\Reader\AcroRd32.exe"),
    Path(r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"),
    Path(r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"),
]


def _utc_now() -> datetime:
    return datetime.utcnow()


def _local_now() -> datetime:
    return _utc_now() + LOCAL_TIME_OFFSET


def _iso(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.replace(microsecond=0).isoformat()


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    return {"items": value}


def _find_adobe_reader() -> str | None:
    for path in ADOBE_READER_CANDIDATES:
        if path.exists():
            return str(path)
    return None


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _powershell_executable() -> str | None:
    if not _is_windows():
        return None
    return (
        shutil.which("powershell.exe")
        or shutil.which("powershell")
        or shutil.which("pwsh.exe")
        or shutil.which("pwsh")
    )


def _cups_command(command: str) -> str | None:
    if _is_windows():
        return None
    return shutil.which(command)


def _printer_identity_fingerprint(identity: PrinterIdentity) -> str:
    return printer_fingerprint(identity)


def _printer_lookup_detail(configured_name: str, resolved_name: str) -> str:
    configured = (configured_name or "").strip()
    resolved = (resolved_name or "").strip()
    if configured and resolved and configured != resolved:
        return f"（配置名 {configured} 已匹配到当前打印机 {resolved}）"
    return ""


def _ambiguous_printer_message(configured_name: str) -> str:
    return f"打印机匹配到多个候选，请重新选择打印机: {configured_name}"


class PrinterResolution:
    def __init__(
        self,
        configured_name: str,
        resolved_name: str,
        *,
        exists: bool = False,
        online: bool | None = None,
        ambiguous: bool = False,
        message: str = "",
    ) -> None:
        self.configured_name = configured_name
        self.resolved_name = resolved_name
        self.exists = exists
        self.online = online
        self.ambiguous = ambiguous
        self.message = message

    @property
    def changed(self) -> bool:
        return bool(self.configured_name and self.resolved_name and self.configured_name != self.resolved_name)


def _dedupe_printer_identities(printers: list[PrinterIdentity]) -> list[PrinterIdentity]:
    result: list[PrinterIdentity] = []
    seen: set[str] = set()
    for printer in printers:
        name = (printer.name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(printer)
    return result


def _printer_is_online(printer: PrinterIdentity) -> bool:
    return printer.online is not False


def _resolve_printer_identity(
    printer_name: str,
    candidates: list[PrinterIdentity],
    *,
    fingerprint: str = "",
) -> PrinterResolution:
    raw_name = (printer_name or "").strip()
    if not raw_name:
        return PrinterResolution(raw_name, "", exists=False, message="未配置打印机名称")

    printers = _dedupe_printer_identities(candidates)
    normalized = normalize_printer_name(raw_name)
    exact_matches = [
        printer
        for printer in printers
        if printer.name == raw_name or normalize_printer_name(printer.name) == normalized
    ]
    if exact_matches:
        exact = exact_matches[0]
        if _printer_is_online(exact):
            return PrinterResolution(raw_name, exact.name, exists=True, online=True)

    online_printers = [printer for printer in printers if _printer_is_online(printer)]
    if fingerprint:
        fingerprint_matches = [
            printer
            for printer in online_printers
            if _printer_identity_fingerprint(printer) == fingerprint
        ]
        if len(fingerprint_matches) == 1:
            return PrinterResolution(raw_name, fingerprint_matches[0].name, exists=True, online=True)
        if len(fingerprint_matches) > 1:
            return PrinterResolution(
                raw_name,
                raw_name,
                exists=True,
                ambiguous=True,
                message=_ambiguous_printer_message(raw_name),
            )

    raw_base = printer_base_name_key(raw_name)
    if not fingerprint and raw_base and raw_base != normalized:
        base_matches = [printer for printer in online_printers if printer_base_name_key(printer.name) == raw_base]
        if len(base_matches) == 1:
            return PrinterResolution(raw_name, base_matches[0].name, exists=True, online=True)
        if len(base_matches) > 1:
            return PrinterResolution(
                raw_name,
                raw_name,
                exists=True,
                ambiguous=True,
                message=_ambiguous_printer_message(raw_name),
            )

    if exact_matches:
        return PrinterResolution(raw_name, exact_matches[0].name, exists=True, online=False)
    return PrinterResolution(raw_name, raw_name, exists=False)


def _print_snapshot(
    *,
    exists: bool,
    offline: bool = False,
    job_count: int = 0,
    job_status: str = "",
    printer_status: str = "",
) -> dict:
    return {
        "exists": exists,
        "offline": offline,
        "job_count": job_count,
        "job_status": job_status,
        "printer_status": printer_status,
    }


def _text_contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lower_text = (text or "").lower()
    return any(token.lower() in lower_text for token in tokens)


def _printer_monitor_snapshot(
    *,
    printer_name: str,
    resolved_printer_name: str = "",
    exists: bool = False,
    paused: bool = False,
    accepting: bool | None = None,
    offline: bool = False,
    job_count: int = 0,
    printer_status: str = "",
    accepting_status: str = "",
    job_status: str = "",
    command_available: bool = True,
    message: str = "",
) -> dict:
    return {
        "printer_name": printer_name,
        "resolved_printer_name": resolved_printer_name or printer_name,
        "exists": exists,
        "paused": paused,
        "accepting": accepting,
        "offline": offline,
        "job_count": job_count,
        "printer_status": printer_status,
        "accepting_status": accepting_status,
        "job_status": job_status,
        "command_available": command_available,
        "message": message,
    }


def _cups_accepting_state(text: str) -> bool | None:
    if not text:
        return None
    lowered = text.lower()
    if "not accepting" in lowered or "不接受" in text or "拒绝" in text:
        return False
    if "accepting" in lowered or "正在接受请求" in text or "接受请求" in text:
        return True
    return None


def _cups_printer_paused(status_text: str) -> bool:
    return _text_contains_any(status_text, ("disabled", "paused", "stopped")) or any(
        token in (status_text or "")
        for token in ("已暂停", "暂停", "已停用", "停用", "禁用")
    )


def _printer_status_offline(status_text: str) -> bool:
    return _text_contains_any(
        status_text,
        (
            "offline",
            "not connected",
            "unplugged",
            "unable to send data",
            "backend failed",
            "filter failed",
        ),
    ) or any(
        token in (status_text or "")
        for token in ("离线", "未连接", "未接入", "无法将数据发送", "设备不可用")
    )


def _cups_printer_monitor_snapshot(printer_name: str) -> dict:
    raw_name = (printer_name or "").strip()
    if not raw_name:
        return _printer_monitor_snapshot(
            printer_name="",
            exists=False,
            command_available=False,
            message="未配置打印机名称",
        )
    lpstat = _cups_command("lpstat")
    if not lpstat:
        return _printer_monitor_snapshot(
            printer_name=raw_name,
            exists=False,
            command_available=False,
            message="CUPS 打印命令 lpstat 不可用",
        )
    resolved_name = _resolve_cups_printer_name(raw_name, lpstat)
    try:
        status_result = subprocess.run(
            [lpstat, "-p", resolved_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return _printer_monitor_snapshot(
            printer_name=raw_name,
            resolved_printer_name=resolved_name,
            exists=False,
            message=f"读取打印机状态失败: {exc}",
        )

    status_text = (status_result.stdout or status_result.stderr or "").strip()
    if status_result.returncode != 0:
        return _printer_monitor_snapshot(
            printer_name=raw_name,
            resolved_printer_name=resolved_name,
            exists=False,
            printer_status=status_text,
            message=status_text or f"打印机不存在: {raw_name}",
        )

    accepting_status = ""
    accepting: bool | None = None
    try:
        accepting_result = subprocess.run(
            [lpstat, "-a", resolved_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
        accepting_status = (accepting_result.stdout or accepting_result.stderr or "").strip()
        if accepting_result.returncode == 0:
            accepting = _cups_accepting_state(accepting_status)
    except Exception as exc:
        accepting_status = str(exc)

    job_status = ""
    job_count = 0
    try:
        jobs_result = subprocess.run(
            [lpstat, "-W", "not-completed", "-o", resolved_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if jobs_result.returncode == 0:
            job_lines = [line.strip() for line in (jobs_result.stdout or "").splitlines() if line.strip()]
            job_count = len(job_lines)
            job_status = "; ".join(job_lines[:3])
        else:
            job_status = (jobs_result.stderr or jobs_result.stdout or "").strip()
    except Exception as exc:
        job_status = str(exc)

    return _printer_monitor_snapshot(
        printer_name=raw_name,
        resolved_printer_name=resolved_name,
        exists=True,
        paused=_cups_printer_paused(status_text),
        accepting=accepting,
        offline=_printer_status_offline("\n".join([status_text, accepting_status, job_status])),
        job_count=job_count,
        printer_status=status_text,
        accepting_status=accepting_status,
        job_status=job_status,
        message="打印机状态已读取",
    )


def _windows_printer_monitor_snapshot(printer_name: str) -> dict:
    raw_name = (printer_name or "").strip()
    if not raw_name:
        return _printer_monitor_snapshot(printer_name="", exists=False, command_available=False, message="未配置打印机名称")
    snapshot = _print_queue_snapshot_windows(raw_name)
    printer_status = str(snapshot.get("printer_status") or "")
    job_status = str(snapshot.get("job_status") or "")
    exists = bool(snapshot.get("exists"))
    paused = _text_contains_any(printer_status, ("paused", "disabled", "stopped"))
    return _printer_monitor_snapshot(
        printer_name=raw_name,
        resolved_printer_name=raw_name,
        exists=exists,
        paused=paused,
        accepting=None,
        offline=bool(snapshot.get("offline")) or _printer_status_offline(f"{printer_status}\n{job_status}"),
        job_count=int(snapshot.get("job_count") or 0),
        printer_status=printer_status,
        job_status=job_status,
        message="打印机状态已读取" if exists else (job_status or f"打印机不存在: {raw_name}"),
    )


def _monitor_printer_snapshot(printer_name: str) -> dict:
    if _is_windows():
        return _windows_printer_monitor_snapshot(printer_name)
    return _cups_printer_monitor_snapshot(printer_name)


def _run_cups_recovery_command(command: str, printer_name: str) -> dict:
    executable = _cups_command(command)
    if not executable:
        return {
            "command": command,
            "returncode": None,
            "ok": False,
            "stdout": "",
            "stderr": f"CUPS 打印命令 {command} 不可用",
        }
    try:
        result = subprocess.run(
            [executable, printer_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "ok": result.returncode == 0,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
        }
    except Exception as exc:
        return {
            "command": command,
            "returncode": None,
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
        }


def _run_windows_recovery_command(printer_name: str) -> list[dict]:
    powershell = _powershell_executable()
    if not powershell:
        return [{"command": "Resume-Printer", "returncode": None, "ok": False, "stdout": "", "stderr": "Windows PowerShell 不可用"}]
    printer_name_ps = _ps_quote(printer_name)
    script = (
        f"Resume-Printer -Name '{printer_name_ps}' -ErrorAction SilentlyContinue; "
        f"Set-Printer -Name '{printer_name_ps}' -WorkOffline $false -ErrorAction SilentlyContinue"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return [
            {
                "command": "Resume-Printer/Set-Printer",
                "returncode": result.returncode,
                "ok": result.returncode == 0,
                "stdout": (result.stdout or "").strip(),
                "stderr": (result.stderr or "").strip(),
            }
        ]
    except Exception as exc:
        return [{"command": "Resume-Printer/Set-Printer", "returncode": None, "ok": False, "stdout": "", "stderr": str(exc)}]


def _recover_printer_once(printer_name: str) -> list[dict]:
    resolved_name = (printer_name or "").strip()
    if not resolved_name:
        return []
    if _is_windows():
        return _run_windows_recovery_command(resolved_name)
    return [
        _run_cups_recovery_command("cupsenable", resolved_name),
        _run_cups_recovery_command("cupsaccept", resolved_name),
    ]


def _printer_monitor_needs_notice(result: dict) -> bool:
    return str(result.get("status") or "") in {"abnormal", "failed", "unsupported"}


def _printer_monitor_recipients(task: ScheduledTask | None, recipients: str | list[str] | None) -> list[str]:
    if isinstance(recipients, list):
        return [str(item).strip() for item in recipients if str(item).strip()]
    raw = str(recipients or "")
    if not raw and task is not None:
        settings = task.settings if isinstance(task.settings, dict) else {}
        raw = str(settings.get("failure_email_recipients") or "")
    return parse_recipients(raw)


def _send_printer_monitor_email(
    db: Session,
    *,
    task: ScheduledTask | None,
    result: dict,
    recipients: list[str],
) -> tuple[bool, str]:
    if not recipients:
        return False, "未配置收件人"
    printer_name = result.get("resolved_printer_name") or result.get("printer_name") or "-"
    subject = f"[CaifuClaw AI] 打印机状态异常：{printer_name}"
    task_lines = []
    if task is not None:
        task_lines = [
            f"任务名称：{task.name}",
            f"任务类型：{task.task_type}",
        ]
    snapshots = result.get("snapshots") or []
    latest_snapshot = snapshots[-1] if snapshots else {}
    attempts = result.get("attempts") or []
    attempt_lines = []
    for attempt in attempts[:5]:
        commands = attempt.get("commands") or []
        command_text = "; ".join(
            f"{item.get('command')} rc={item.get('returncode')} {item.get('stderr') or item.get('stdout') or ''}".strip()
            for item in commands
        )
        attempt_lines.append(f"- 第 {attempt.get('attempt')} 次：{command_text or '无命令输出'}")
    if len(attempts) > 5:
        attempt_lines.append(f"- 其余 {len(attempts) - 5} 次请登录后台查看")
    body = "\n".join(
        [
            "系统检测到打印机状态异常，自动恢复未成功或无需恢复但需要人工检查。",
            "",
            *task_lines,
            f"打印机：{printer_name}",
            f"状态：{result.get('status') or '-'}",
            f"说明：{result.get('message') or '-'}",
            f"是否存在：{'是' if latest_snapshot.get('exists') else '否'}",
            f"是否暂停：{'是' if latest_snapshot.get('paused') else '否'}",
            f"是否离线：{'是' if latest_snapshot.get('offline') else '否'}",
            f"是否接收任务：{latest_snapshot.get('accepting')}",
            f"队列任务数：{latest_snapshot.get('job_count') or 0}",
            "",
            "打印机状态：",
            str(latest_snapshot.get("printer_status") or "-"),
            "",
            "接收任务状态：",
            str(latest_snapshot.get("accepting_status") or "-"),
            "",
            "恢复尝试：",
            *(attempt_lines or ["- 未执行恢复命令"]),
            "",
            "请检查打印机电源、纸张、USB 连接和 macOS 打印队列。",
        ]
    )
    try:
        send_email(get_email_setting(db), recipients, subject, body)
        return True, "打印机异常通知邮件已发送"
    except Exception as exc:
        return False, f"打印机异常通知邮件发送失败：{exc}"


def _printer_monitor_wecom_content(result: dict) -> str:
    printer_name = str(result.get("resolved_printer_name") or result.get("printer_name") or "-").strip() or "-"
    message = str(result.get("message") or "").replace("\n", " ").strip("；;。 ")
    if len(message) > 160:
        message = f"{message[:160]}..."
    if message:
        return f"打印机异常：{printer_name}，{message}。"
    return f"打印机异常：{printer_name}。"


def _send_printer_monitor_wecom(db: Session, *, result: dict) -> tuple[bool, str]:
    try:
        settings = load_wecom_robot_settings_from_db(db)
        with WeComRobotClient(settings) as client:
            client.send_text(_printer_monitor_wecom_content(result), use_default_mentions=False)
        return True, "打印机异常企业微信通知已发送"
    except Exception as exc:
        return False, f"打印机异常企业微信通知发送失败：{exc}"


def monitor_printer_status(
    db: Session,
    printer_name: str,
    *,
    task: ScheduledTask | None = None,
    recipients: str | list[str] | None = None,
    auto_recover: bool = True,
    max_retries: int = 3,
    send_notifications: bool = True,
) -> dict:
    raw_name = (printer_name or "").strip()
    max_retries = min(max(int(max_retries or 0), 1), 10)
    snapshots: list[dict] = []
    attempts: list[dict] = []
    snapshot = _monitor_printer_snapshot(raw_name)
    snapshots.append(snapshot)
    result = {
        "printer_name": raw_name,
        "resolved_printer_name": snapshot.get("resolved_printer_name") or raw_name,
        "status": "ok",
        "message": "打印机状态正常",
        "exists": bool(snapshot.get("exists")),
        "paused": bool(snapshot.get("paused")),
        "accepting": snapshot.get("accepting"),
        "offline": bool(snapshot.get("offline")),
        "job_count": int(snapshot.get("job_count") or 0),
        "recovered": False,
        "recovery_attempts": 0,
        "email_sent": False,
        "email_error": "",
        "wecom_sent": False,
        "wecom_error": "",
        "attempts": attempts,
        "snapshots": snapshots,
    }

    if not snapshot.get("command_available", True):
        result.update(status="unsupported", message=snapshot.get("message") or "打印命令不可用")
    elif not snapshot.get("exists"):
        result.update(status="abnormal", message=snapshot.get("message") or f"打印机不存在: {raw_name}")
    else:
        needs_recovery = bool(snapshot.get("paused")) or snapshot.get("accepting") is False
        if auto_recover and needs_recovery:
            resolved_name = str(snapshot.get("resolved_printer_name") or raw_name)
            for attempt_no in range(1, max_retries + 1):
                commands = _recover_printer_once(resolved_name)
                time.sleep(1)
                snapshot = _monitor_printer_snapshot(raw_name)
                snapshots.append(snapshot)
                attempts.append({"attempt": attempt_no, "commands": commands, "snapshot": snapshot})
                result["recovery_attempts"] = attempt_no
                result.update(
                    resolved_printer_name=snapshot.get("resolved_printer_name") or resolved_name,
                    exists=bool(snapshot.get("exists")),
                    paused=bool(snapshot.get("paused")),
                    accepting=snapshot.get("accepting"),
                    offline=bool(snapshot.get("offline")),
                    job_count=int(snapshot.get("job_count") or 0),
                )
                if snapshot.get("exists") and not snapshot.get("paused") and snapshot.get("accepting") is not False and not snapshot.get("offline"):
                    result.update(status="recovered", recovered=True, message=f"打印机已恢复，尝试 {attempt_no} 次")
                    break
            else:
                result.update(status="failed", message=f"打印机暂停/拒收任务，尝试恢复 {max_retries} 次仍未成功")
        elif needs_recovery:
            result.update(status="abnormal", message="打印机处于暂停或不接受任务状态")
        elif bool(snapshot.get("offline")):
            result.update(status="abnormal", message="打印机处于离线或连接异常状态")
        elif snapshot.get("accepting") is False:
            result.update(status="abnormal", message="打印机当前不接受新任务")

    if send_notifications and _printer_monitor_needs_notice(result):
        notice_messages = []
        parsed_recipients = _printer_monitor_recipients(task, recipients)
        email_sent, email_message = _send_printer_monitor_email(db, task=task, result=result, recipients=parsed_recipients)
        result["email_sent"] = email_sent
        if not email_sent:
            result["email_error"] = email_message
        else:
            result["email_error"] = ""
        notice_messages.append(email_message)
        wecom_sent, wecom_message = _send_printer_monitor_wecom(db, result=result)
        result["wecom_sent"] = wecom_sent
        result["wecom_error"] = "" if wecom_sent else wecom_message
        notice_messages.append(wecom_message)
        result["message"] = "；".join(
            part for part in [str(result.get("message") or ""), *notice_messages] if part
        ).strip("；")

    return result


def _unique_printer_names_for_monitor(targets: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for target in targets:
        name = (target or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _run_printer_monitor_step(
    db: Session,
    task: ScheduledTask,
    run: ScheduledTaskRun,
    printer_names: list[str],
) -> list[dict]:
    unique_names = _unique_printer_names_for_monitor(printer_names)
    step = _start_step(
        db,
        run.id,
        STEP_MONITOR_PRINTER_STATUS,
        "检查并恢复打印机状态",
        {"printers": unique_names, "max_retries": 3},
    )
    results: list[dict] = []
    try:
        for printer_name in unique_names:
            try:
                results.append(
                    monitor_printer_status(
                        db,
                        printer_name,
                        task=task,
                        auto_recover=True,
                        max_retries=3,
                        send_notifications=False,
                    )
                )
            except Exception as exc:
                results.append(
                    {
                        "printer_name": printer_name,
                        "resolved_printer_name": printer_name,
                        "status": "error",
                        "message": f"打印机状态监控调用异常: {exc}",
                        "email_sent": False,
                        "email_error": "",
                        "wecom_sent": False,
                        "wecom_error": "",
                    }
                )
        issue_count = sum(1 for item in results if str(item.get("status") or "") not in {"ok", "recovered"})
        email_count = sum(1 for item in results if item.get("email_sent"))
        wecom_count = sum(1 for item in results if item.get("wecom_sent"))
        message = f"打印机状态监控完成，检查 {len(unique_names)} 台，异常 {issue_count} 台，邮件通知 {email_count} 台，企微通知 {wecom_count} 台"
        _finish_step(
            db,
            step,
            status="success",
            message=message,
            stats={
                "printer_count": len(unique_names),
                "issue_count": issue_count,
                "email_count": email_count,
                "wecom_count": wecom_count,
                "results": results,
            },
        )
        return results
    except Exception as exc:
        _finish_step(
            db,
            step,
            status="success",
            message=f"打印机状态监控步骤异常但不影响主流程: {exc}",
            stats={"printer_count": len(unique_names), "error": str(exc), "results": results},
        )
        return results


_CUPS_QUEUE_JOB_ID_RE = re.compile(
    r"(?:request\s+id\s+is|请求\s*(?:id|ID|编号)\s*是?)\s*([^\s(（]+-\d+)",
    re.IGNORECASE,
)


def _cups_queue_job_id(print_message: str) -> str:
    match = _CUPS_QUEUE_JOB_ID_RE.search(print_message or "")
    return match.group(1).strip() if match else ""


def _post_print_monitor_printers(db: Session, run_id: int) -> list[dict]:
    rows = db.scalars(
        select(ScheduledTaskRunOrder)
        .where(
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.print_submitted.is_(True),
            ScheduledTaskRunOrder.printer_name != "",
        )
        .order_by(asc(ScheduledTaskRunOrder.id))
    ).all()
    grouped: dict[str, dict] = {}
    seen_jobs: set[tuple[str, str]] = set()
    for row in rows:
        printer_name = (row.printer_name or "").strip()
        document_name = (row.print_job_name or "").strip()
        queue_job_id = "" if _is_windows() else _cups_queue_job_id(row.print_message or "")
        job_key = queue_job_id or document_name
        if not printer_name or not job_key or (printer_name, job_key) in seen_jobs:
            continue
        seen_jobs.add((printer_name, job_key))
        printer = grouped.setdefault(printer_name, {"printer_name": printer_name, "jobs": []})
        printer["jobs"].append(
            {
                "queue_job_id": queue_job_id,
                "document_name": document_name,
            }
        )
    return list(grouped.values())


def _initialize_post_print_monitor(
    db: Session,
    run: ScheduledTaskRun,
    stats: dict | None,
    *,
    now: datetime,
) -> dict:
    data = dict(_json_object(stats))
    if run.task_type != TASK_TYPE_AUTO_ORDER_PIPELINE or not run.id:
        return data
    try:
        printers = _post_print_monitor_printers(db, int(run.id))
    except Exception:
        logger.exception("Failed to initialize post-print monitor run_id=%s", run.id)
        return data
    if not printers:
        return data
    data[POST_PRINT_MONITOR_KEY] = {
        "status": "active",
        "started_at": _iso(now),
        "expires_at": _iso(now + POST_PRINT_MONITOR_DURATION),
        "check_interval_seconds": POST_PRINT_MONITOR_INTERVAL_SECONDS,
        "last_checked_at": "",
        "check_count": 0,
        "notified_printers": [],
        "notification_count": 0,
        "last_notification_at": "",
        "last_notification_error": "",
        "printers": printers,
        "last_results": [],
    }
    return data


def _parse_monitor_datetime(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _cups_not_completed_job_ids(printer_name: str) -> set[str] | None:
    lpstat = _cups_command("lpstat")
    if not lpstat:
        return None
    resolved_name = _resolve_cups_printer_name(printer_name, lpstat)
    try:
        result = subprocess.run(
            [lpstat, "-W", "not-completed", "-o", resolved_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return {
        line.split(maxsplit=1)[0]
        for line in (result.stdout or "").splitlines()
        if line.strip()
    }


def _post_print_pending_jobs(printer: dict) -> list[dict] | None:
    printer_name = str(printer.get("printer_name") or "").strip()
    jobs = [item for item in (printer.get("jobs") or []) if isinstance(item, dict)]
    if not printer_name:
        return []
    if _is_windows():
        pending: list[dict] = []
        for job in jobs:
            document_name = str(job.get("document_name") or "").strip()
            if document_name and int(_print_queue_snapshot_windows(printer_name, document_name).get("job_count") or 0) > 0:
                pending.append(job)
        return pending
    pending_ids = _cups_not_completed_job_ids(printer_name)
    if pending_ids is None:
        return None
    return [job for job in jobs if str(job.get("queue_job_id") or "") in pending_ids]


def _post_print_printer_is_abnormal(snapshot: dict) -> bool:
    return (
        not bool(snapshot.get("exists"))
        or bool(snapshot.get("paused"))
        or bool(snapshot.get("offline"))
    )


def _recover_post_print_printer(printer_name: str, initial_snapshot: dict) -> tuple[bool, list[dict], dict]:
    snapshot = initial_snapshot
    attempts: list[dict] = []
    for attempt_no in range(1, POST_PRINT_MONITOR_MAX_RECOVERY_ATTEMPTS + 1):
        commands = _recover_printer_once(str(snapshot.get("resolved_printer_name") or printer_name))
        time.sleep(1)
        snapshot = _monitor_printer_snapshot(printer_name)
        attempts.append({"attempt": attempt_no, "commands": commands})
        if not _post_print_printer_is_abnormal(snapshot):
            return True, attempts, snapshot
    return False, attempts, snapshot


def _post_print_monitor_reason(snapshot: dict) -> str:
    parts = [
        str(snapshot.get("printer_status") or "").strip(),
        str(snapshot.get("job_status") or "").strip(),
        str(snapshot.get("message") or "").strip(),
    ]
    text = " ".join(part.replace("\n", " ") for part in parts if part)
    return (text[:240] + "...") if len(text) > 240 else (text or "打印机状态异常")


def _post_print_monitor_wecom_content(
    run: ScheduledTaskRun,
    task: ScheduledTask | None,
    incidents: list[dict],
) -> str:
    lines = [
        "打印任务异常",
        f"定时任务：{task.name if task else run.task_type}",
        f"运行ID：{run.id}",
        "",
    ]
    for index, incident in enumerate(incidents, start=1):
        job_ids = [
            str(job.get("queue_job_id") or job.get("document_name") or "").strip()
            for job in incident.get("pending_jobs") or []
            if str(job.get("queue_job_id") or job.get("document_name") or "").strip()
        ]
        lines.extend(
            [
                f"{index}. {incident.get('printer_name') or '-'}",
                f"未完成任务：{len(job_ids)}",
                f"队列任务：{', '.join(job_ids) or '-'}",
                f"原因：{incident.get('reason') or '-'}",
                f"自动恢复：{'成功，原队列继续处理' if incident.get('recovered') else '失败，请人工处理'}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _send_post_print_monitor_wecom(
    db: Session,
    *,
    run: ScheduledTaskRun,
    task: ScheduledTask | None,
    incidents: list[dict],
) -> tuple[bool, str]:
    try:
        settings = load_wecom_robot_settings_from_db(db)
        with WeComRobotClient(settings) as client:
            client.send_text(
                _post_print_monitor_wecom_content(run, task, incidents),
                use_default_mentions=False,
            )
        return True, "打印任务异常汇总企微通知已发送"
    except Exception as exc:
        return False, f"打印任务异常汇总企微通知发送失败：{exc}"


def _process_post_print_monitor_run(
    db: Session,
    run: ScheduledTaskRun,
    *,
    now: datetime,
) -> bool:
    stats = dict(_json_object(run.stats_json))
    monitor = dict(stats.get(POST_PRINT_MONITOR_KEY) or {})
    if monitor.get("status") != "active":
        return False

    expires_at = _parse_monitor_datetime(monitor.get("expires_at"))
    if expires_at is None or now > expires_at:
        monitor["status"] = "expired"
        monitor["completed_at"] = _iso(now)
        stats[POST_PRINT_MONITOR_KEY] = monitor
        run.stats_json = stats
        return True

    notified_printers = {
        str(item).strip()
        for item in (monitor.get("notified_printers") or [])
        if str(item).strip()
    }
    incidents: list[dict] = []
    results: list[dict] = []
    has_pending_jobs = False
    pending_check_failed = False

    for printer in monitor.get("printers") or []:
        if not isinstance(printer, dict):
            continue
        printer_name = str(printer.get("printer_name") or "").strip()
        pending_jobs = _post_print_pending_jobs(printer)
        if pending_jobs is None:
            pending_check_failed = True
            results.append({"printer_name": printer_name, "status": "check_failed", "pending_job_count": None})
            continue
        if not pending_jobs:
            results.append({"printer_name": printer_name, "status": "queue_cleared", "pending_job_count": 0})
            continue

        has_pending_jobs = True
        snapshot = _monitor_printer_snapshot(printer_name)
        abnormal = _post_print_printer_is_abnormal(snapshot)
        result = {
            "printer_name": printer_name,
            "status": "abnormal" if abnormal else "pending",
            "pending_job_count": len(pending_jobs),
            "pending_job_ids": [
                str(job.get("queue_job_id") or job.get("document_name") or "")
                for job in pending_jobs
            ],
        }
        results.append(result)
        if not abnormal or printer_name in notified_printers:
            continue

        recovered, attempts, final_snapshot = _recover_post_print_printer(printer_name, snapshot)
        incidents.append(
            {
                "printer_name": printer_name,
                "pending_jobs": pending_jobs,
                "reason": _post_print_monitor_reason(snapshot),
                "recovered": recovered,
                "recovery_attempts": len(attempts),
                "final_status": _post_print_monitor_reason(final_snapshot),
            }
        )

    task = db.get(ScheduledTask, run.scheduled_task_id) if run.scheduled_task_id else None
    if incidents:
        sent, message = _send_post_print_monitor_wecom(db, run=run, task=task, incidents=incidents)
        monitor["last_notification_error"] = "" if sent else message
        if sent:
            notified_printers.update(str(item.get("printer_name") or "") for item in incidents)
            monitor["notification_count"] = int(monitor.get("notification_count") or 0) + 1
            monitor["last_notification_at"] = _iso(now)

    monitor["last_checked_at"] = _iso(now)
    monitor["check_count"] = int(monitor.get("check_count") or 0) + 1
    monitor["notified_printers"] = sorted(item for item in notified_printers if item)
    monitor["last_results"] = results
    if not has_pending_jobs and not pending_check_failed:
        monitor["status"] = "completed"
        monitor["completed_at"] = _iso(now)

    stats[POST_PRINT_MONITOR_KEY] = monitor
    run.stats_json = stats
    return True


def process_post_print_monitors(*, now: datetime | None = None) -> int:
    current = now or _utc_now()
    db = SessionLocal()
    processed = 0
    try:
        runs = db.scalars(
            select(ScheduledTaskRun)
            .where(
                ScheduledTaskRun.task_type == TASK_TYPE_AUTO_ORDER_PIPELINE,
                ScheduledTaskRun.ended_at.is_not(None),
                ScheduledTaskRun.ended_at >= current - timedelta(days=1),
            )
            .order_by(ScheduledTaskRun.id.desc())
            .limit(100)
        ).all()
        for run in runs:
            try:
                if _process_post_print_monitor_run(db, run, now=current):
                    processed += 1
            except Exception:
                logger.exception("Post-print monitor failed run_id=%s", run.id)
        if processed:
            db.commit()
    finally:
        db.close()
    return processed


def _parse_cups_status_printer_name(text: str) -> str:
    if text.startswith("printer "):
        parts = text.split(maxsplit=2)
        return parts[1] if len(parts) >= 2 else ""
    if not text.startswith("打印机"):
        return ""
    value = text.removeprefix("打印机").strip()
    if not value or value.startswith(("已", "正在")):
        return ""
    markers = ["现在", " 正在", " 闲置", "闲置", "已", "禁用", "启用", "，", ",", "。"]
    end_positions = [value.find(marker) for marker in markers if value.find(marker) > 0]
    return value[:min(end_positions)].strip() if end_positions else value


def _cups_printer_devices(lpstat: str) -> dict[str, str]:
    try:
        result = subprocess.run([lpstat, "-v"], capture_output=True, text=True, timeout=20)
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    devices: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        text = line.strip()
        if not text:
            continue
        if text.lower().startswith("device for ") and ":" in text:
            name, uri = text[len("device for "):].split(":", 1)
            devices[name.strip()] = uri.strip()
            continue
        match = re.match(r"^用于(.+?)的设备[:：]\s*(.+)$", text)
        if match:
            devices[match.group(1).strip()] = match.group(2).strip()
    return devices


def _cups_printer_identities(lpstat: str) -> list[PrinterIdentity]:
    try:
        result = subprocess.run([lpstat, "-p"], capture_output=True, text=True, timeout=20)
    except Exception:
        return []
    statuses: dict[str, str] = {}
    current_name = ""
    for raw_line in (result.stdout or "").splitlines():
        raw = raw_line.rstrip()
        text = raw.strip()
        if not text:
            continue
        if raw[:1].isspace() and current_name:
            statuses[current_name] = "\n".join(part for part in [statuses.get(current_name, ""), text] if part)
            continue
        name = _parse_cups_status_printer_name(text)
        if not name:
            continue
        current_name = name
        statuses[name] = text
    devices = _cups_printer_devices(lpstat)
    names = sorted(set(devices) | set(statuses), key=lambda value: value.lower())
    identities: list[PrinterIdentity] = []
    for name in names:
        status_text = statuses.get(name, "")
        lower_status = status_text.lower()
        offline = any(token in lower_status for token in ("disabled", "offline", "not connected", "unplugged"))
        offline = offline or any(token in status_text for token in ("离线", "禁用", "未连接", "未接入"))
        identities.append(
            PrinterIdentity(
                name=name,
                system="cups",
                device_uri=devices.get(name, ""),
                status=status_text,
                online=not offline if status_text else None,
            )
        )
    return identities


def _resolve_cups_printer_name(printer_name: str, lpstat: str | None = None) -> str:
    raw_name = (printer_name or "").strip()
    if not raw_name:
        return ""
    lpstat = lpstat or _cups_command("lpstat")
    if not lpstat:
        return raw_name
    return _resolve_printer_identity(raw_name, _cups_printer_identities(lpstat)).resolved_name


def _windows_printer_identities() -> list[PrinterIdentity]:
    command = r"""
$default = $null
try {
  $default = (Get-CimInstance Win32_Printer | Where-Object { $_.Default -eq $true } | Select-Object -First 1).Name
} catch {}
try {
  $items = @(Get-Printer -ErrorAction Stop | Sort-Object Name | ForEach-Object {
    [pscustomobject]@{
      Name=$_.Name
      DriverName=$_.DriverName
      PortName=$_.PortName
      PrinterStatus=($_.PrinterStatus -as [string])
      WorkOffline=([bool]$_.WorkOffline)
      IsDefault=($_.Name -eq $default)
    }
  })
} catch {
  $items = @(Get-CimInstance Win32_Printer | Sort-Object Name | ForEach-Object {
    [pscustomobject]@{
      Name=$_.Name
      DriverName=$_.DriverName
      PortName=$_.PortName
      PrinterStatus=($_.PrinterStatus -as [string])
      WorkOffline=([bool]$_.WorkOffline)
      IsDefault=([bool]$_.Default)
    }
  })
}
$items | ConvertTo-Json -Compress
"""
    try:
        result = _run_powershell(command, timeout=20)
    except Exception:
        return []
    if result is None or result.returncode != 0:
        return []
    try:
        data = json.loads((result.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    identities: list[PrinterIdentity] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name") or "").strip()
        if not name:
            continue
        status = str(item.get("PrinterStatus") or "")
        work_offline = bool(item.get("WorkOffline"))
        identities.append(
            PrinterIdentity(
                name=name,
                system="windows",
                driver_name=str(item.get("DriverName") or ""),
                port_name=str(item.get("PortName") or ""),
                status=status,
                online=not (work_offline or "offline" in status.lower()),
            )
        )
    return identities


def _server_printer_identities() -> list[PrinterIdentity]:
    if _is_windows():
        return _windows_printer_identities()
    lpstat = _cups_command("lpstat")
    return _cups_printer_identities(lpstat) if lpstat else []


def _resolve_printer_for_setting(setting: PlatformPrintSetting | None, fallback_name: str = "") -> tuple[PrinterResolution, list[PrinterIdentity]]:
    printer_name = (setting.printer_name or "").strip() if setting else (fallback_name or "").strip()
    printers = _server_printer_identities()
    fingerprint = _configured_printer_fingerprint(setting)
    return _resolve_printer_identity(printer_name, printers, fingerprint=fingerprint), printers


def _run_powershell(command: str, *, timeout: int) -> subprocess.CompletedProcess | None:
    powershell = _powershell_executable()
    if not powershell:
        return None
    return subprocess.run(
        [powershell, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _reader_process_ids() -> set[int]:
    try:
        result = _run_powershell(
            "Get-Process AcroRd32,Acrobat -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }",
            timeout=10,
        )
        if result is None:
            return set()
        ids: set[int] = set()
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                ids.add(int(line))
        return ids
    except Exception:
        return set()


def _close_reader_processes(process_ids: set[int]) -> None:
    if not process_ids:
        return
    ids = ",".join(str(pid) for pid in sorted(process_ids))
    try:
        _run_powershell(f"Stop-Process -Id {ids} -Force -ErrorAction SilentlyContinue", timeout=10)
    except Exception:
        pass


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _safe_print_job_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:180] or "caifuclaw-ai-print"


def _build_print_job_name(*parts: object) -> str:
    platform = next((str(part) for part in parts if part and not str(part).startswith(("run", "order")) and str(part) not in ("auto", "retry")), "unknown")
    platform = _safe_print_job_name(platform).replace("-", "_")
    timestamp = _local_now().strftime("%Y%m%d%H%M%S%f")
    return f"label_print_{platform}_{timestamp}.pdf"

def _orientation_adjusted_pdf_path(
    pdf_path: str,
    page_orientation: str | None,
    target_size_mm: tuple[float, float] | None = None,
) -> tuple[str, str | None]:
    orientation = normalize_print_orientation(page_orientation)
    if orientation == PRINT_ORIENTATION_AUTO and not target_size_mm:
        return pdf_path, None
    adjusted = orient_pdf_bytes(Path(pdf_path).read_bytes(), orientation, target_size_mm=target_size_mm)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        temp_file.write(adjusted)
        temp_file.flush()
        return temp_file.name, temp_file.name
    finally:
        temp_file.close()


def _cups_orientation_options(page_orientation: str | None) -> list[str]:
    orientation = normalize_print_orientation(page_orientation)
    if orientation == PRINT_ORIENTATION_PORTRAIT:
        return ["-o", "orientation-requested=3"]
    if orientation == PRINT_ORIENTATION_LANDSCAPE:
        return ["-o", "orientation-requested=4"]
    return []


def _format_cups_mm(value: float) -> str:
    rounded = round(float(value), 2)
    if abs(rounded - round(rounded)) < 0.01:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _format_cups_points(value: float) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _cups_custom_media_from_mm(size_mm: tuple[float, float]) -> str:
    width_mm, height_mm = size_mm
    width_points = float(width_mm) * 72.0 / 25.4
    height_points = float(height_mm) * 72.0 / 25.4
    return f"Custom.{_format_cups_points(width_points)}x{_format_cups_points(height_points)}"


def _pdf_first_page_size_mm(pdf_path: str) -> tuple[float, float] | None:
    try:
        from pypdf import PdfReader

        page = PdfReader(pdf_path).pages[0]
        width = float(page.mediabox.width) * 25.4 / 72.0
        height = float(page.mediabox.height) * 25.4 / 72.0
        rotation = int(page.get("/Rotate", 0) or 0) % 180
        if rotation == 90:
            return height, width
        return width, height
    except Exception:
        return None


def _cups_media_options(pdf_path: str, target_size_mm: tuple[float, float] | None) -> list[str]:
    if target_size_mm:
        custom_media = _cups_custom_media_from_mm(target_size_mm)
    else:
        page_size = _pdf_first_page_size_mm(pdf_path)
        if not page_size:
            return []
        width_mm, height_mm = page_size
        custom_media = f"Custom.{_format_cups_mm(width_mm)}x{_format_cups_mm(height_mm)}mm"
    return ["-o", f"media={custom_media}", "-o", f"PageSize={custom_media}"]


def _printer_devmode_for_orientation(printer_handle, page_orientation: str | None):
    orientation = normalize_print_orientation(page_orientation)
    if orientation == PRINT_ORIENTATION_AUTO:
        return None
    if not all([win32con, win32print]):
        return None
    try:
        properties = win32print.GetPrinter(printer_handle, 2)
        devmode = properties.get("pDevMode") if isinstance(properties, dict) else None
        if devmode is None:
            return None
        if hasattr(devmode, "Fields") and hasattr(win32con, "DM_ORIENTATION"):
            devmode.Fields |= win32con.DM_ORIENTATION
        devmode.Orientation = (
            win32con.DMORIENT_LANDSCAPE
            if orientation == PRINT_ORIENTATION_LANDSCAPE
            else win32con.DMORIENT_PORTRAIT
        )
        return devmode
    except Exception:
        return None


def _create_printer_dc(printer_name: str, page_orientation: str | None, printer_handle):
    hdc = win32ui.CreateDC()
    devmode = _printer_devmode_for_orientation(printer_handle, page_orientation)
    if devmode is not None:
        try:
            hdc.CreateDC("WINSPOOL", printer_name, None, devmode)
            return hdc
        except Exception:
            try:
                hdc.DeleteDC()
            except Exception:
                pass
            hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    return hdc


def _image_for_print_orientation(image, page_orientation: str | None):
    orientation = normalize_print_orientation(page_orientation)
    if orientation == PRINT_ORIENTATION_LANDSCAPE and image.height > image.width:
        return image.rotate(90, expand=True)
    if orientation == PRINT_ORIENTATION_PORTRAIT and image.width > image.height:
        return image.rotate(90, expand=True)
    return image


def _submit_pdf_to_printer_gdi(
    pdf_path: str,
    printer_name: str,
    job_name: str,
    page_orientation: str | None = PRINT_ORIENTATION_AUTO,
) -> tuple[bool, str]:
    if not all([fitz, win32con, win32print, win32ui, Image, ImageWin]):
        return False, "GDI 静默打印组件不可用"

    document_name = _safe_print_job_name(job_name or Path(pdf_path).name)
    if not document_name.lower().endswith(".pdf"):
        document_name = f"{document_name}.pdf"

    printer_handle = None
    hdc = None
    doc_started = False
    try:
        printer_handle = win32print.OpenPrinter(printer_name)
        hdc = _create_printer_dc(printer_name, page_orientation, printer_handle)
        dpi_x = max(1, int(hdc.GetDeviceCaps(win32con.LOGPIXELSX)))
        dpi_y = max(1, int(hdc.GetDeviceCaps(win32con.LOGPIXELSY)))
        printable_width = max(1, int(hdc.GetDeviceCaps(win32con.HORZRES)))
        printable_height = max(1, int(hdc.GetDeviceCaps(win32con.VERTRES)))

        doc = fitz.open(pdf_path)
        if doc.page_count <= 0:
            return False, "PDF 没有可打印页面"

        hdc.StartDoc(document_name)
        doc_started = True
        for page in doc:
            matrix = fitz.Matrix(dpi_x / 72.0, dpi_y / 72.0)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            image = _image_for_print_orientation(image, page_orientation)
            scale = min(printable_width / image.width, printable_height / image.height)
            draw_width = max(1, int(image.width * scale))
            draw_height = max(1, int(image.height * scale))
            if draw_width != image.width or draw_height != image.height:
                image = image.resize((draw_width, draw_height), Image.Resampling.LANCZOS)
            dib = ImageWin.Dib(image)
            hdc.StartPage()
            dib.draw(hdc.GetHandleOutput(), (0, 0, draw_width, draw_height))
            hdc.EndPage()
        hdc.EndDoc()
        doc.close()
        return True, f"已提交打印队列: {printer_name}，任务名: {document_name}"
    except Exception as exc:
        if hdc is not None and doc_started:
            try:
                hdc.AbortDoc()
            except Exception:
                pass
        return False, f"GDI 静默打印失败: {exc}"
    finally:
        if hdc is not None:
            try:
                hdc.DeleteDC()
            except Exception:
                pass
        if printer_handle is not None:
            try:
                win32print.ClosePrinter(printer_handle)
            except Exception:
                pass


def _print_queue_snapshot_windows(printer_name: str, document_name: str = "") -> dict:
    if not printer_name:
        return _print_snapshot(exists=False)
    printer_name_ps = _ps_quote(printer_name)
    document_name_ps = _ps_quote(document_name)
    command = f"""
$printer = Get-Printer -Name '{printer_name_ps}' -ErrorAction SilentlyContinue
if ($null -eq $printer) {{
  [pscustomobject]@{{Exists=$false;Offline=$false;JobCount=0;JobStatus='';PrinterStatus='missing'}} | ConvertTo-Json -Compress
  exit 0
}}
$cim = Get-CimInstance Win32_Printer | Where-Object {{ $_.Name -eq '{printer_name_ps}' }} | Select-Object -First 1
$offline = (($printer.PrinterStatus -eq 'Offline') -or ($printer.WorkOffline -eq $true) -or ($null -ne $cim -and $cim.WorkOffline -eq $true))
$jobs = @(Get-PrintJob -PrinterName '{printer_name_ps}' -ErrorAction SilentlyContinue)
if ('{document_name_ps}' -ne '') {{
  $jobs = @($jobs | Where-Object {{ $_.DocumentName -eq '{document_name_ps}' }})
}}
$job = $jobs | Select-Object -First 1
[pscustomobject]@{{
  Exists=$true
  Offline=[bool]$offline
  JobCount=$jobs.Count
  JobStatus=($job.JobStatus -as [string])
  PrinterStatus=($printer.PrinterStatus -as [string])
}} | ConvertTo-Json -Compress
"""
    try:
        result = _run_powershell(command, timeout=20)
        if result is None:
            return _print_snapshot(exists=True, job_status="Windows PowerShell 不可用", printer_status="unsupported")
        if result.returncode != 0:
            return _print_snapshot(exists=True, job_status=result.stderr.strip(), printer_status="unknown")
        data = json.loads((result.stdout or "{}").strip() or "{}")
        return _print_snapshot(
            exists=bool(data.get("Exists")),
            offline=bool(data.get("Offline")),
            job_count=int(data.get("JobCount") or 0),
            job_status=data.get("JobStatus") or "",
            printer_status=data.get("PrinterStatus") or "",
        )
    except Exception as exc:
        return _print_snapshot(exists=True, job_status=str(exc), printer_status="unknown")


def _print_queue_snapshot_cups(printer_name: str, document_name: str = "") -> dict:
    if not printer_name:
        return _print_snapshot(exists=False)
    lpstat = _cups_command("lpstat")
    if not lpstat:
        return _print_snapshot(exists=True, job_status="CUPS 打印命令 lpstat 不可用", printer_status="unsupported")
    printer_name = _resolve_cups_printer_name(printer_name, lpstat)
    try:
        status_result = subprocess.run(
            [lpstat, "-p", printer_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return _print_snapshot(exists=True, job_status=str(exc), printer_status="unknown")

    status_text = (status_result.stdout or status_result.stderr or "").strip()
    if status_result.returncode != 0:
        return _print_snapshot(exists=False, job_status=status_text, printer_status="missing")

    lowered_status = status_text.lower()
    offline = any(token in lowered_status for token in ("disabled", "offline", "not connected", "unplugged"))
    try:
        jobs_result = subprocess.run(
            [lpstat, "-W", "not-completed", "-o", printer_name],
            capture_output=True,
            text=True,
            timeout=20,
        )
        job_lines = [line.strip() for line in (jobs_result.stdout or "").splitlines() if line.strip()] if jobs_result.returncode == 0 else []
    except Exception as exc:
        return _print_snapshot(exists=True, offline=offline, job_status=str(exc), printer_status=status_text or "unknown")

    if document_name:
        document_matches = [line for line in job_lines if document_name in line]
        if document_matches:
            job_lines = document_matches
    return _print_snapshot(
        exists=True,
        offline=offline,
        job_count=len(job_lines),
        job_status="; ".join(job_lines[:3]),
        printer_status=status_text,
    )


def _print_queue_snapshot(printer_name: str, document_name: str = "") -> dict:
    if _is_windows():
        return _print_queue_snapshot_windows(printer_name, document_name)
    return _print_queue_snapshot_cups(printer_name, document_name)


def _run_dto(row: ScheduledTaskRun) -> dict:
    return {
        "id": row.id,
        "scheduled_task_id": row.scheduled_task_id,
        "task_type": row.task_type,
        "trigger_mode": row.trigger_mode or "",
        "status": row.status or "",
        "summary": row.summary or "",
        "stats_json": row.stats_json or {},
        "attempt_no": int(row.attempt_no or 0),
        "max_retry_count": int(row.max_retry_count or 0),
        "parent_run_id": row.parent_run_id,
        "original_run_id": row.original_run_id,
        "next_retry_at": _iso(row.next_retry_at),
        "retry_reason": row.retry_reason or "",
        "email_sent": bool(row.email_sent),
        "email_error": row.email_error or "",
        "started_at": _iso(row.started_at),
        "ended_at": _iso(row.ended_at),
        "created_at": _iso(row.created_at),
    }


def _step_dto(row: ScheduledTaskRunStep) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "step_code": row.step_code,
        "step_name": row.step_name,
        "status": row.status or "",
        "message": row.message or "",
        "stats_json": row.stats_json or {},
        "payload_json": row.payload_json or {},
        "started_at": _iso(row.started_at),
        "ended_at": _iso(row.ended_at),
    }


def _run_order_dto(row: ScheduledTaskRunOrder) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "order_id": row.order_id,
        "platform": row.platform or "",
        "purchase_order_id": row.purchase_order_id,
        "pdf_generated": bool(row.pdf_generated),
        "pdf_file_path": row.pdf_file_path or "",
        "printer_name": row.printer_name or "",
        "print_job_name": row.print_job_name or "",
        "print_submitted": bool(row.print_submitted),
        "print_message": row.print_message or "",
        "status_before": row.status_before or "",
        "status_after": row.status_after or "",
        "needs_reprint": bool(row.needs_reprint),
        "error_message": row.error_message or "",
        "created_at": _iso(row.created_at),
    }


def _settings_int(settings: dict, key: str, default: int, *, min_value: int = 0, max_value: int = 100000) -> int:
    try:
        value = int(settings.get(key) if settings.get(key) not in (None, "") else default)
    except (TypeError, ValueError):
        value = default
    return min(max(value, min_value), max_value)


def _task_retry_count(task: ScheduledTask) -> int:
    return _settings_int(_task_settings(task), "retry_count", 0, min_value=0, max_value=20)


def _task_retry_interval_minutes(task: ScheduledTask) -> int:
    return _settings_int(_task_settings(task), "retry_interval_minutes", 10, min_value=1, max_value=1440)


def _task_timeout_seconds(task: ScheduledTask) -> int:
    minutes = _settings_int(_task_settings(task), "timeout_minutes", 30, min_value=1, max_value=1440)
    return minutes * 60


def _task_poll_interval_seconds(task: ScheduledTask) -> int:
    settings = _task_settings(task)
    if settings.get("interval_minutes") not in (None, ""):
        minutes = _settings_int(settings, "interval_minutes", 3, min_value=1, max_value=24 * 60)
        return minutes * 60
    return _settings_int(settings, "poll_interval_seconds", 180, min_value=10, max_value=24 * 60 * 60)


def _task_logistics_ready_timeout_seconds(task: ScheduledTask) -> int:
    configured_seconds = _settings_int(
        _task_settings(task),
        "logistics_ready_timeout_seconds",
        DEFAULT_LOGISTICS_READY_TIMEOUT_SECONDS,
        min_value=0,
        max_value=24 * 60 * 60,
    )
    if configured_seconds <= 0:
        return configured_seconds
    task_timeout = _task_timeout_seconds(task)
    max_wait_seconds = max(0, task_timeout - TASK_TIMEOUT_COMPLETION_BUFFER_SECONDS)
    return min(configured_seconds, max_wait_seconds)


def _task_logistics_ready_poll_seconds(task: ScheduledTask) -> int:
    return _settings_int(
        _task_settings(task),
        "logistics_ready_poll_seconds",
        DEFAULT_LOGISTICS_READY_POLL_SECONDS,
        min_value=1,
        max_value=10 * 60,
    )


def _run_age_seconds(run: ScheduledTaskRun, now: datetime) -> float:
    started_at = run.started_at
    if not started_at:
        return 0
    if started_at.tzinfo is not None:
        started_at = started_at.replace(tzinfo=None)
    return max(0.0, (now - started_at).total_seconds())


def mark_stale_scheduled_task_runs(db: Session, *, now: datetime | None = None) -> int:
    now = (now or _utc_now()).replace(tzinfo=None)
    earliest_cutoff = now - timedelta(seconds=60 + STALE_RUNNING_TASK_BUFFER_SECONDS)
    rows = db.scalars(
        select(ScheduledTaskRun).where(
            ScheduledTaskRun.status == "running",
            ScheduledTaskRun.ended_at.is_(None),
            ScheduledTaskRun.started_at < earliest_cutoff,
        )
    ).all()
    marked_count = 0
    task_cache: dict[int, ScheduledTask | None] = {}
    for run in rows:
        task: ScheduledTask | None = None
        if run.scheduled_task_id:
            task_id = int(run.scheduled_task_id)
            if task_id not in task_cache:
                task_cache[task_id] = db.get(ScheduledTask, task_id)
            task = task_cache[task_id]
        timeout_seconds = _task_timeout_seconds(task) if task is not None else 30 * 60
        stale_after_seconds = timeout_seconds + STALE_RUNNING_TASK_BUFFER_SECONDS
        if _run_age_seconds(run, now) < stale_after_seconds:
            continue

        timeout_minutes = max(1, timeout_seconds // 60)
        summary = f"任务运行超时或服务重启，已由 watchdog 标记失败（超过 {timeout_minutes} 分钟未结束）"
        run.status = "failed"
        run.summary = summary
        run.stats_json = _json_object(run.stats_json)
        run.ended_at = now
        run.next_retry_at = None
        run.retry_reason = ""
        if task is not None and (not task.last_run_at or not run.started_at or task.last_run_at <= run.started_at):
            task.last_run_at = now
            task.last_status = "failed"
            task.last_message = summary

        running_steps = db.scalars(
            select(ScheduledTaskRunStep).where(
                ScheduledTaskRunStep.run_id == run.id,
                ScheduledTaskRunStep.status == "running",
                ScheduledTaskRunStep.ended_at.is_(None),
            )
        ).all()
        for step in running_steps:
            step.status = "failed"
            step.message = summary if not step.message else f"{step.message}；{summary}"
            step.ended_at = now
        marked_count += 1
    return marked_count


def _create_run(
    db: Session,
    task: ScheduledTask,
    trigger_mode: str,
    *,
    attempt_no: int = 0,
    parent_run_id: int | None = None,
    original_run_id: int | None = None,
) -> ScheduledTaskRun:
    run = ScheduledTaskRun(
        scheduled_task_id=task.id,
        task_type=task.task_type or TASK_TYPE_AUTO_ORDER_PIPELINE,
        trigger_mode=trigger_mode,
        status="running",
        summary="",
        stats_json={},
        attempt_no=attempt_no,
        max_retry_count=_task_retry_count(task),
        parent_run_id=parent_run_id,
        original_run_id=original_run_id,
        started_at=_utc_now(),
        created_at=_utc_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _previous_chain_run_ids(db: Session, run: ScheduledTaskRun) -> list[int]:
    root_run_id = run.original_run_id or run.parent_run_id
    if not root_run_id:
        return []
    rows = db.scalars(
        select(ScheduledTaskRun.id)
        .where(
            ScheduledTaskRun.id < run.id,
            or_(ScheduledTaskRun.id == root_run_id, ScheduledTaskRun.original_run_id == root_run_id),
        )
        .order_by(asc(ScheduledTaskRun.id))
    ).all()
    return [int(row_id) for row_id in rows]


def _retry_source_order_ids(db: Session, run: ScheduledTaskRun) -> list[int]:
    previous_run_ids = _previous_chain_run_ids(db, run)
    if not previous_run_ids:
        return []
    rows = db.scalars(
        select(ScheduledTaskRunOrder.order_id)
        .where(ScheduledTaskRunOrder.run_id.in_(previous_run_ids))
        .order_by(asc(ScheduledTaskRunOrder.id))
    ).all()
    order_ids: list[int] = []
    seen: set[int] = set()
    for order_id in rows:
        if order_id not in seen:
            order_ids.append(order_id)
            seen.add(order_id)
    return order_ids


def _select_orders_for_run(db: Session, run: ScheduledTaskRun) -> tuple[list[Order], bool]:
    retry_order_ids = _retry_source_order_ids(db, run)
    if not retry_order_ids:
        return _select_pending_orders_for_run(db), False
    rows = db.scalars(select(Order).where(Order.id.in_(retry_order_ids))).all()
    row_map = {row.id: row for row in rows}
    return [row_map[order_id] for order_id in retry_order_ids if order_id in row_map], True


def _previous_printed_rows(db: Session, run: ScheduledTaskRun) -> dict[int, ScheduledTaskRunOrder]:
    previous_run_ids = _previous_chain_run_ids(db, run)
    if not previous_run_ids:
        return {}
    rows = db.scalars(
        select(ScheduledTaskRunOrder)
        .where(
            ScheduledTaskRunOrder.run_id.in_(previous_run_ids),
            ScheduledTaskRunOrder.print_submitted == True,
        )
        .order_by(asc(ScheduledTaskRunOrder.id))
    ).all()
    result: dict[int, ScheduledTaskRunOrder] = {}
    for row in rows:
        result[row.order_id] = row
    return result


def _finish_run(
    db: Session,
    run: ScheduledTaskRun,
    task: ScheduledTask | None,
    *,
    status: str,
    summary: str,
    stats: dict | None = None,
) -> ScheduledTaskRun:
    now = _utc_now()
    run.status = status
    run.summary = summary
    run.stats_json = _initialize_post_print_monitor(db, run, stats, now=now)
    run.ended_at = now
    if task is not None:
        task.last_run_at = now
        task.last_status = status
        task.last_message = summary
    db.commit()
    db.refresh(run)
    if task is not None:
        db.refresh(task)
    return run


def _start_step(db: Session, run_id: int, step_code: str, step_name: str, payload: dict | None = None) -> ScheduledTaskRunStep:
    step = ScheduledTaskRunStep(
        run_id=run_id,
        step_code=step_code,
        step_name=step_name,
        status="running",
        message="",
        stats_json={},
        payload_json=payload or {},
        started_at=_utc_now(),
        created_at=_utc_now(),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def _finish_step(
    db: Session,
    step: ScheduledTaskRunStep,
    *,
    status: str,
    message: str,
    stats: dict | None = None,
    payload: dict | None = None,
) -> ScheduledTaskRunStep:
    step.status = status
    step.message = message
    step.stats_json = _json_object(stats)
    if payload is not None:
        step.payload_json = _json_object(payload)
    step.ended_at = _utc_now()
    db.commit()
    db.refresh(step)
    return step


def _upsert_run_order(db: Session, run_id: int, order: Order, **updates) -> ScheduledTaskRunOrder:
    row = db.scalar(
        select(ScheduledTaskRunOrder).where(
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.order_id == order.id,
        )
    )
    if row is None:
        row = ScheduledTaskRunOrder(
            run_id=run_id,
            order_id=order.id,
            platform=order.platform or "",
            status_before=order.biz_status or "",
            status_after=order.biz_status or "",
            created_at=_utc_now(),
        )
        db.add(row)
        db.flush()
    for key, value in updates.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def _upsert_run_document(db: Session, run_id: int, platform: str, **updates) -> ScheduledTaskRunOrder:
    if not all(hasattr(db, name) for name in ("scalar", "add", "flush", "commit", "refresh")):
        return ScheduledTaskRunOrder(
            run_id=run_id,
            order_id=0,
            platform=platform or "",
            status_before="",
            status_after="",
            created_at=_utc_now(),
            **updates,
        )
    row = db.scalar(
        select(ScheduledTaskRunOrder).where(
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.order_id == 0,
        )
    )
    if row is None:
        row = ScheduledTaskRunOrder(
            run_id=run_id,
            order_id=0,
            platform=platform or "",
            status_before="",
            status_after="",
            created_at=_utc_now(),
        )
        db.add(row)
        db.flush()
    row.platform = platform or row.platform or ""
    for key, value in updates.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def _latest_shipment(db: Session, order_id: int) -> Shipment | None:
    from .main import _latest_shipment as latest_shipment

    return latest_shipment(db, order_id)


async def _ensure_labels_cached(db: Session, rows: list[Order], load_bytes: bool = True) -> tuple[dict[int, bytes], int, int, int]:
    from .main import _ensure_labels_cached as ensure_labels_cached

    return await ensure_labels_cached(db, rows, load_bytes=load_bytes)


async def _ensure_labels_cached_for_readiness(db: Session, rows: list[Order]) -> tuple[dict[int, bytes], int, int, int]:
    return await _ensure_labels_cached(db, rows, load_bytes=True)


def _printer_setting_map(db: Session) -> dict[str, PlatformPrintSetting]:
    rows = db.scalars(
        select(PlatformPrintSetting)
        .where(PlatformPrintSetting.enabled == True, PlatformPrintSetting.document_type == PRINT_DOCUMENT_TYPE_LABEL)
        .order_by(asc(PlatformPrintSetting.id))
    ).all()
    return {row.platform: row for row in rows}


def _printer_identity_from_setting(setting: PlatformPrintSetting | None) -> PrinterIdentity | None:
    if not setting:
        return None
    name = (getattr(setting, "printer_name", "") or "").strip()
    if not name:
        return None
    return PrinterIdentity(
        name=name,
        system=getattr(setting, "printer_system", "") or "",
        device_uri=getattr(setting, "printer_device_uri", "") or "",
        driver_name=getattr(setting, "printer_driver_name", "") or "",
        port_name=getattr(setting, "printer_port_name", "") or "",
    )


def _configured_printer_fingerprint(setting: PlatformPrintSetting | None) -> str:
    if not setting:
        return ""
    saved = (getattr(setting, "printer_fingerprint", "") or "").strip()
    if saved:
        return saved
    identity = _printer_identity_from_setting(setting)
    return _printer_identity_fingerprint(identity) if identity else ""


def _apply_resolved_printer_to_setting(
    db: Session,
    setting: PlatformPrintSetting | None,
    resolved_name: str,
    printers: list[PrinterIdentity],
) -> None:
    if not setting or not resolved_name or resolved_name == (setting.printer_name or ""):
        return
    resolved = next((printer for printer in printers if printer.name == resolved_name), None)
    if not resolved:
        return
    setting.printer_name = resolved.name
    setting.printer_system = resolved.system or ""
    setting.printer_device_uri = resolved.device_uri or ""
    setting.printer_driver_name = resolved.driver_name or ""
    setting.printer_port_name = resolved.port_name or ""
    setting.printer_fingerprint = _printer_identity_fingerprint(resolved)
    setting.updated_at = _utc_now()
    db.flush()


def _task_settings(task: ScheduledTask) -> dict:
    settings = task.settings or {}
    return settings if isinstance(settings, dict) else {}


def _select_pending_orders_for_run(db: Session) -> list[Order]:
    rows = db.scalars(
        select(Order)
        .where(
            or_(
                and_(
                    Order.biz_status == ORDER_STATUS_PENDING,
                    Order.label_printed_at.is_(None),
                    or_(Order.local_status.is_(None), Order.local_status != "fbj_follow_up_pending"),
                ),
                and_(Order.biz_status == ORDER_STATUS_WAITING_PRINT, Order.label_printed_at.is_(None)),
                _waiting_purchase_condition(),
            )
        )
        .order_by(asc(Order.payment_at).nulls_last(), asc(Order.id))
    ).all()
    return rows


def _has_purchase_order_for_order(order_id: int):
    return exists().where(PurchaseOrderSource.order_id == order_id)


def _waiting_purchase_condition():
    return and_(
        Order.biz_status == ORDER_STATUS_WAITING_PURCHASE,
        or_(Order.label_printed_at.is_not(None), Order.is_overseas_warehouse == True),
        ~_has_purchase_order_for_order(Order.id),
    )


def _order_tracking_number(db: Session, row: Order) -> str:
    tracking_number = clean_tracking_number(
        getattr(row, "shipment_tracking_number", ""),
        getattr(row, "raw_payload", None) or {},
        getattr(row, "platform", None),
    )
    if tracking_number:
        return tracking_number
    shipment = _latest_shipment(db, row.id)
    if shipment:
        shipment_tracking = clean_tracking_number(
            shipment.tracking_number,
            getattr(row, "raw_payload", None) or {},
            getattr(row, "platform", None),
        )
        if shipment_tracking:
            return shipment_tracking
    platform_tracking = _platform_tracking_number_from_posting(row)
    if platform_tracking:
        return platform_tracking
    return ""


def _order_display_number(row: Order) -> str:
    return row.platform_order_no or row.posting_number or row.platform_order_id or str(row.id)


def _platform_tracking_number_from_posting(row: Order) -> str:
    if str(getattr(row, "platform", "") or "").lower() == "ozon":
        payload = getattr(row, "raw_payload", None) if isinstance(getattr(row, "raw_payload", None), dict) else {}
        status = str(getattr(row, "platform_status", "") or payload.get("status") or "").strip().lower()
        substatus = str(payload.get("substatus") or "").strip().lower()
        if status in {"awaiting_packaging", "awaiting_registration"} or substatus == "posting_created":
            return ""
        if not status:
            return ""
        return str(getattr(row, "posting_number", "") or "").strip()
    return ""


def _tracking_number_from_payload(raw_payload: dict | None) -> str:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    candidates = [
        payload.get("tracking_number"),
        payload.get("shipment_tracking_number"),
        payload.get("trackingCode"),
        payload.get("tracking_code"),
        payload.get("track_number"),
        payload.get("trackNumber"),
    ]
    shipment = payload.get("shipment")
    if isinstance(shipment, dict):
        candidates.extend(
            [
                shipment.get("tracking_number"),
                shipment.get("trackingCode"),
                shipment.get("tracking_code"),
                shipment.get("track_number"),
            ]
        )
    for value in candidates:
        text = clean_tracking_number(value, payload)
        if text:
            return text
    return ""


def _order_tracking_number_value(db: Session, row: Order) -> str:
    tracking_number = clean_tracking_number(
        getattr(row, "shipment_tracking_number", ""),
        getattr(row, "raw_payload", None) or {},
        getattr(row, "platform", None),
    )
    if tracking_number:
        return tracking_number
    payload_tracking = _tracking_number_from_payload(getattr(row, "raw_payload", None) or {})
    if payload_tracking:
        return payload_tracking
    shipment = _latest_shipment(db, row.id)
    if shipment:
        shipment_tracking = clean_tracking_number(
            shipment.tracking_number,
            getattr(row, "raw_payload", None) or {},
            getattr(row, "platform", None),
        )
        if shipment_tracking:
            return shipment_tracking
    platform_tracking = _platform_tracking_number_from_posting(row)
    if platform_tracking:
        return platform_tracking
    return ""


def _order_tracking_log_suffix(db: Session, row: Order) -> str:
    tracking_number = _order_tracking_number_value(db, row)
    return f"，货运单号：{tracking_number}" if tracking_number else ""


def _parse_datetime_value(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _effective_shipping_deadline(row: Order) -> datetime | None:
    raw_payload = getattr(row, "raw_payload", None)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    candidates = [
        getattr(row, "shipping_deadline_at", None),
        payload.get("shipping_deadline_at"),
        payload.get("shipment_date"),
        payload.get("platform_handover_deadline"),
        payload.get("ship_by_date"),
        payload.get("delivery_date_begin"),
    ]
    for value in candidates:
        parsed = _parse_datetime_value(value)
        if parsed:
            return parsed
    return None


def _order_chinese_product_name_map(db: Session, rows: list[Order]) -> dict[int, str]:
    if not rows or not hasattr(db, "execute"):
        return {}

    order_ids = [row.id for row in rows]
    account_pairs = {
        (
            getattr(row, "platform", ""),
            getattr(row, "shop_id", None) or getattr(row, "account_id", None) or "",
        )
        for row in rows
    }
    account_id_map: dict[tuple[str, str], int] = {}
    if account_pairs:
        platform_values = {platform for platform, _account_id in account_pairs}
        account_values = {account_id for _platform, account_id in account_pairs}
        accounts = db.scalars(
            select(PlatformAccount).where(
                PlatformAccount.platform.in_(platform_values),
                PlatformAccount.account_id.in_(account_values),
            )
        ).all()
        account_id_map = {(account.platform, account.account_id): account.id for account in accounts}

    shop_db_whens = [
        (
            OrderItem.order_id == row.id,
            account_id_map.get(
                (
                    getattr(row, "platform", ""),
                    getattr(row, "shop_id", None) or getattr(row, "account_id", None) or "",
                )
            ),
        )
        for row in rows
        if account_id_map.get(
            (
                getattr(row, "platform", ""),
                getattr(row, "shop_id", None) or getattr(row, "account_id", None) or "",
            )
        )
        is not None
    ]
    if not shop_db_whens:
        return {}

    shop_db_case = case(*shop_db_whens, else_=None)
    mapping_choice = mapping_choice_for_order_item(shop_db_case)
    product_name = func.coalesce(mapping_choice["exact_product"].internal_name, mapping_choice["insensitive_product"].internal_name)
    result: dict[int, str] = {}
    query_rows = db.execute(
        select(
            OrderItem.order_id,
            product_name.label("product_name"),
        )
        .select_from(OrderItem)
        .outerjoin(mapping_choice["exact_mapping"], mapping_choice["exact_condition"])
        .outerjoin(mapping_choice["exact_product"], mapping_choice["exact_product"].id == mapping_choice["exact_mapping"].product_id)
        .outerjoin(mapping_choice["insensitive_mapping"], mapping_choice["insensitive_condition"])
        .outerjoin(
            mapping_choice["insensitive_product"],
            mapping_choice["insensitive_product"].id == mapping_choice["insensitive_mapping"].product_id,
        )
        .where(OrderItem.order_id.in_(order_ids))
        .order_by(OrderItem.id.asc())
    ).all()
    for order_id, product_name in query_rows:
        current = result.get(int(order_id), "")
        value = str(product_name or "").strip()
        if value and value not in current.split(" / "):
            result[int(order_id)] = " / ".join(part for part in [current, value] if part)
        else:
            result.setdefault(int(order_id), current)
    return result


def _chinese_label_rows_for_orders(db: Session, rows: list[Order]) -> list[ChineseLabelRow]:
    product_name_map = _order_chinese_product_name_map(db, rows)
    return [
        ChineseLabelRow(
            tracking_number=_order_tracking_number_value(db, row),
            deadline=resolve_chinese_label_deadline(
                platform=getattr(row, "platform", None),
                payment_at=getattr(row, "payment_at", None),
                platform_created_at=getattr(row, "platform_created_at", None),
                imported_at=getattr(row, "created_at", None),
                fallback=_effective_shipping_deadline(row),
            ),
            product_name=product_name_map.get(row.id, ""),
        )
        for row in rows
    ]


def _orders_with_tracking(db: Session, rows: list[Order]) -> list[Order]:
    result: list[Order] = []
    for row in rows:
        if order_is_overseas_warehouse(row) or order_is_logistics_label_exempt(row) or _order_tracking_number(db, row):
            result.append(row)
    return result


def _orders_missing_tracking(db: Session, rows: list[Order]) -> list[Order]:
    tracked_ids = {row.id for row in _orders_with_tracking(db, rows)}
    return [row for row in rows if row.id not in tracked_ids]


def _is_wildberries_cross_border_label_tracking_order(row: Order) -> bool:
    if str(getattr(row, "platform", "") or "").lower() != "wildberries":
        return False
    raw_payload = getattr(row, "raw_payload", None)
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    supply = payload.get("supply") if isinstance(payload.get("supply"), dict) else {}
    cross_border_type = str(payload.get("crossBorderType") or supply.get("crossBorderType") or "").strip()
    return cross_border_type == "1"


def _label_candidate_rows_for_readiness(db: Session, rows: list[Order], tracking_rows: list[Order]) -> list[Order]:
    tracking_ids = {row.id for row in tracking_rows}
    candidates = [
        row
        for row in rows
        if row.id in tracking_ids or _is_wildberries_cross_border_label_tracking_order(row)
    ]
    return [
        row
        for row in candidates
        if not order_is_overseas_warehouse(row) and not order_is_logistics_label_exempt(row)
    ]


def _is_mercadolibre_delivered_order(row: Order) -> bool:
    return (
        str(getattr(row, "platform", "") or "").strip().lower() == "mercadolibre"
        and str(getattr(row, "platform_status", "") or "").strip().lower() == "delivered"
    )


def _logistics_failed_count(stats: dict) -> int:
    return (
        int(stats.get("submit_failed", 0) or 0)
        + int(stats.get("failed_accounts", 0) or 0)
        + int(stats.get("refresh_failed_accounts", 0) or 0)
        + int(stats.get("label_failed", 0) or 0)
    )


async def _append_readiness_stats(db: Session, rows: list[Order], stats: dict) -> dict:
    tracking_rows = _orders_with_tracking(db, rows)
    # A delivered MercadoLibre shipment cannot return a label from the platform.
    # Resolve it from its tracking number without making a doomed label request.
    label_rows = [
        row
        for row in _label_candidate_rows_for_readiness(db, rows, tracking_rows)
        if not _is_mercadolibre_delivered_order(row)
    ]
    if label_rows:
        _pdf_map, cached, fetched, failed = await _ensure_labels_cached_for_readiness(db, label_rows)
    else:
        _pdf_map, cached, fetched, failed = {}, 0, 0, 0
    tracking_rows = _orders_with_tracking(db, rows)
    overseas_rows = [row for row in tracking_rows if order_is_overseas_warehouse(row)]
    exempt_rows = [row for row in tracking_rows if not order_is_overseas_warehouse(row) and order_is_logistics_label_exempt(row)]
    label_ready_rows = [
        row
        for row in tracking_rows
        if not order_is_overseas_warehouse(row) and not order_is_logistics_label_exempt(row) and bool(_pdf_map.get(row.id))
    ]
    label_ready_order_ids = (
        [row.id for row in overseas_rows]
        + [row.id for row in exempt_rows]
        + [row.id for row in label_ready_rows]
    )
    label_ready_ids = set(label_ready_order_ids)
    delivered_without_label_order_ids = [
        row.id
        for row in tracking_rows
        if row.id not in label_ready_ids and _is_mercadolibre_delivered_order(row)
    ]
    result = dict(stats or {})
    result["label_cached"] = int(cached or 0)
    result["label_fetched"] = int(fetched or 0)
    result["label_failed"] = int(failed or 0)
    result["overseas_warehouse_ready_count"] = len(overseas_rows)
    result["logistics_label_exempt_ready_count"] = len(exempt_rows)
    result["tracking_ready_count"] = len(tracking_rows)
    result["tracking_ready_order_ids"] = [row.id for row in tracking_rows]
    result["label_ready_order_ids"] = label_ready_order_ids
    result["delivered_without_label_order_ids"] = delivered_without_label_order_ids
    return result


async def _refresh_order_status_and_labels(
    db: Session,
    rows: list[Order],
    *,
    eligible_statuses: set[str],
) -> dict:
    status_stats = await refresh_order_logistics_for_rows(
        db,
        rows,
        eligible_statuses=eligible_statuses,
        preserve_biz_status=True,
    )
    stats = dict(status_stats or {})
    stats["stage"] = "status_refresh"
    return await _append_readiness_stats(db, rows, stats)


async def _sync_logistics_and_labels(
    db: Session,
    rows: list[Order],
    *,
    eligible_statuses: set[str],
    readiness_rows: list[Order] | None = None,
) -> dict:
    logistics_stats = await submit_platform_shipments_and_refresh_logistics(
        db,
        rows,
        eligible_statuses=eligible_statuses,
        preserve_biz_status_on_refresh=True,
    )
    stats = dict(logistics_stats or {})
    stats["stage"] = "sync_logistics"
    stats["synced_order_ids"] = [row.id for row in rows]
    return await _append_readiness_stats(db, readiness_rows or rows, stats)


def _ready_rows_from_sync_stats(rows: list[Order], sync_stats: dict) -> tuple[list[Order], dict]:
    tracking_ids = set(sync_stats.get("tracking_ready_order_ids") or [])
    ready_ids = set(sync_stats.get("label_ready_order_ids") or [])
    delivered_without_label_ids = set(sync_stats.get("delivered_without_label_order_ids") or []) - ready_ids
    resolved_ids = ready_ids | delivered_without_label_ids
    ready_rows = [row for row in rows if row.id in ready_ids]
    return ready_rows, {
        "total": len(rows),
        "tracking_ready_count": len(tracking_ids),
        "ready_count": len(ready_rows),
        "ready_order_ids": sorted(ready_ids),
        "resolved_order_ids": sorted(resolved_ids),
        "delivered_without_label_count": len(delivered_without_label_ids),
        "delivered_without_label_order_ids": sorted(delivered_without_label_ids),
        "tracking_pending_count": len([row for row in rows if row.id not in tracking_ids]),
        "label_pending_count": len(tracking_ids - resolved_ids),
        "label_cached": int(sync_stats.get("label_cached", 0) or 0),
        "label_fetched": int(sync_stats.get("label_fetched", 0) or 0),
        "label_failed": int(sync_stats.get("label_failed", 0) or 0),
    }


async def _orders_ready_for_print(db: Session, rows: list[Order]) -> tuple[list[Order], dict]:
    tracking_rows = _orders_with_tracking(db, rows)
    label_rows = _label_candidate_rows_for_readiness(db, rows, tracking_rows)
    if label_rows:
        pdf_map, cached, fetched, failed = await _ensure_labels_cached_for_readiness(db, label_rows)
    else:
        pdf_map, cached, fetched, failed = {}, 0, 0, 0
    tracking_rows = _orders_with_tracking(db, rows)
    overseas_rows = [row for row in tracking_rows if order_is_overseas_warehouse(row)]
    exempt_rows = [row for row in tracking_rows if not order_is_overseas_warehouse(row) and order_is_logistics_label_exempt(row)]
    label_ready_rows = [
        row
        for row in tracking_rows
        if not order_is_overseas_warehouse(row) and not order_is_logistics_label_exempt(row) and bool(pdf_map.get(row.id))
    ]
    ready_rows = overseas_rows + exempt_rows + label_ready_rows
    ready_ids = {row.id for row in ready_rows}
    tracking_ids = {row.id for row in tracking_rows}
    return ready_rows, {
        "total": len(rows),
        "tracking_ready_count": len(tracking_rows),
        "ready_count": len(ready_rows),
        "tracking_pending_count": len([row for row in rows if row.id not in tracking_ids]),
        "label_pending_count": len([row for row in tracking_rows if row.id not in ready_ids]),
        "label_cached": int(cached or 0),
        "label_fetched": int(fetched or 0),
        "label_failed": int(failed or 0),
        "overseas_warehouse_ready_count": len(overseas_rows),
        "logistics_label_exempt_ready_count": len(exempt_rows),
    }


async def _wait_for_logistics_and_labels_ready(
    db: Session,
    task: ScheduledTask,
    rows: list[Order],
    *,
    eligible_statuses: set[str],
) -> tuple[list[Order], dict]:
    attempts: list[dict] = []
    first_stats = await _refresh_order_status_and_labels(db, rows, eligible_statuses=eligible_statuses)
    attempts.append({"attempt": 1, "stage": "status_refresh", "stats": first_stats})
    ready_rows, readiness = _ready_rows_from_sync_stats(rows, first_stats)
    resolved_ids = set(readiness.get("resolved_order_ids") or [])
    if len(resolved_ids) == len(rows):
        return ready_rows, {
            "attempts": attempts,
            "readiness": readiness,
            "timed_out": False,
            "waited_seconds": 0,
        }

    sync_rows = [row for row in rows if row.id not in resolved_ids]
    if sync_rows:
        sync_stats = await _sync_logistics_and_labels(
            db,
            sync_rows,
            eligible_statuses=eligible_statuses,
            readiness_rows=rows,
        )
        attempts.append({"attempt": 2, "stage": "sync_logistics", "stats": sync_stats})
        ready_rows, readiness = _ready_rows_from_sync_stats(rows, sync_stats)
        resolved_ids = set(readiness.get("resolved_order_ids") or [])
        if len(resolved_ids) == len(rows):
            return ready_rows, {
                "attempts": attempts,
                "readiness": readiness,
                "timed_out": False,
                "waited_seconds": 0,
            }

        if _logistics_failed_count(sync_stats) > 0:
            retry_rows = [row for row in rows if row.id not in resolved_ids]
            retry_stats = await _sync_logistics_and_labels(
                db,
                retry_rows,
                eligible_statuses=eligible_statuses,
                readiness_rows=rows,
            )
            attempts.append({"attempt": 3, "stage": "sync_logistics_retry", "stats": retry_stats})
            ready_rows, readiness = _ready_rows_from_sync_stats(rows, retry_stats)
            resolved_ids = set(readiness.get("resolved_order_ids") or [])
            if len(resolved_ids) == len(rows):
                return ready_rows, {
                    "attempts": attempts,
                    "readiness": readiness,
                    "timed_out": False,
                    "waited_seconds": 0,
                }

    timeout_seconds = _task_logistics_ready_timeout_seconds(task)
    poll_seconds = _task_logistics_ready_poll_seconds(task)
    if timeout_seconds <= 0:
        return ready_rows, {
            "attempts": attempts,
            "readiness": readiness,
            "timed_out": len(resolved_ids) != len(rows),
            "waited_seconds": 0,
        }

    deadline = time.monotonic() + timeout_seconds
    waited_seconds = 0
    while len(resolved_ids) != len(rows):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sleep_seconds = min(poll_seconds, max(0.0, remaining))
        await asyncio.sleep(sleep_seconds)
        waited_seconds += int(round(sleep_seconds))
        sync_rows = [row for row in rows if row.id not in resolved_ids]
        if not sync_rows:
            break
        poll_stats = await _sync_logistics_and_labels(
            db,
            sync_rows,
            eligible_statuses=eligible_statuses,
            readiness_rows=rows,
        )
        attempts.append({"attempt": len(attempts) + 1, "stats": poll_stats})
        ready_rows, readiness = _ready_rows_from_sync_stats(rows, poll_stats)
        resolved_ids = set(readiness.get("resolved_order_ids") or [])

    return ready_rows, {
        "attempts": attempts,
        "readiness": readiness,
        "timed_out": len(resolved_ids) != len(rows),
        "waited_seconds": min(waited_seconds, timeout_seconds),
    }


def _move_to_picking(db: Session, rows: list[Order]) -> None:
    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_PICKING
        row.local_status = "picking"
        row.picking_at = row.picking_at or now
        row.updated_at = now
    add_order_operation_logs(
        db,
        rows,
        operation_type="to_picking",
        operation_attribute="修改订单基础信息",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 已转入配货中，"
            f"状态：{ORDER_STATUS_WAITING_PURCHASE} -> {ORDER_STATUS_PICKING}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
    )
    db.commit()


def _move_to_printing(db: Session, rows: list[Order]) -> None:
    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_WAITING_PRINT
        row.updated_at = now
    add_order_operation_logs(
        db,
        rows,
        operation_type="to_printing",
        operation_attribute="修改订单基础信息",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 已转入待打印，"
            f"状态：{ORDER_STATUS_PENDING} -> {ORDER_STATUS_WAITING_PRINT}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
    )
    db.commit()


def _move_to_waiting_purchase(db: Session, rows: list[Order]) -> None:
    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_WAITING_PURCHASE
        row.updated_at = now
    add_order_operation_logs(
        db,
        rows,
        operation_type="to_waiting_purchase",
        operation_attribute="修改订单基础信息",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 打印完成，"
            f"状态：{ORDER_STATUS_WAITING_PRINT} -> {ORDER_STATUS_WAITING_PURCHASE}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
    )
    db.commit()


def _mark_labels_printed(db: Session, order_ids: list[int]) -> None:
    if not order_ids:
        return
    now = _utc_now()
    rows = db.scalars(select(Order).where(Order.id.in_(order_ids))).all()
    newly_printed_rows = []
    for row in rows:
        if row.label_printed_at is None:
            row.label_printed_at = now
            newly_printed_rows.append(row)
        row.updated_at = now
    add_order_operation_logs(
        db,
        newly_printed_rows,
        operation_type="print_label",
        operation_attribute="打印面单",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 面单已提交打印"
            + _order_tracking_log_suffix(db, order)
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
    )
    db.commit()


def _generate_purchase_order_for_orders(db: Session, rows: list[Order]) -> PurchaseOrder:
    from .main import _generate_purchase_order_for_orders as generate_purchase_order_for_orders

    return generate_purchase_order_for_orders(db, rows, SYSTEM_OPERATOR, "", allow_existing=True)


def _move_to_picking_after_purchase(db: Session, rows: list[Order], purchase: PurchaseOrder) -> None:
    from .main import _move_orders_to_picking_after_purchase

    _move_orders_to_picking_after_purchase(
        db,
        rows,
        purchase,
        SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        description=f"定时任务：已生成采购单 {purchase.purchase_no}，订单已转入配货中",
    )
    db.commit()


def _purchase_missing_product_name_rows(db: Session, rows: list[Order]) -> tuple[list[Order], list[Order], list[dict]]:
    order_ids = [row.id for row in rows]
    if not order_ids:
        return [], [], []
    if not hasattr(db, "execute"):
        return rows, [], []
    order_map = {row.id: row for row in rows}
    mapping_choice = mapping_choice_for_order_item()
    product_name = func.coalesce(mapping_choice["exact_product"].internal_name, mapping_choice["insensitive_product"].internal_name)
    query_rows = db.execute(
        select(
            Order.id,
            Order.platform_order_no,
            Order.posting_number,
            Order.platform_order_id,
            OrderItem.id,
            OrderItem.sku,
            product_name.label("product_name"),
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .outerjoin(
            PlatformAccount,
            (PlatformAccount.platform == Order.platform) & (PlatformAccount.account_id == Order.shop_id),
        )
        .outerjoin(mapping_choice["exact_mapping"], mapping_choice["exact_condition"])
        .outerjoin(mapping_choice["exact_product"], mapping_choice["exact_product"].id == mapping_choice["exact_mapping"].product_id)
        .outerjoin(mapping_choice["insensitive_mapping"], mapping_choice["insensitive_condition"])
        .outerjoin(
            mapping_choice["insensitive_product"],
            mapping_choice["insensitive_product"].id == mapping_choice["insensitive_mapping"].product_id,
        )
        .where(Order.id.in_(order_ids))
    ).all()
    seen_order_ids = {int(item[0]) for item in query_rows}
    missing_order_ids: set[int] = set()
    details: list[dict] = []
    for order_id, platform_order_no, posting_number, platform_order_id, item_id, sku, product_name in query_rows:
        if not product_name:
            missing_order_ids.add(int(order_id))
            details.append(
                {
                    "order_id": int(order_id),
                    "order_no": platform_order_no or posting_number or platform_order_id or str(order_id),
                    "order_item_id": int(item_id),
                    "sku": sku or "",
                    "reason": "产品中文名称为空",
                }
            )
    for order_id in order_ids:
        if order_id not in seen_order_ids:
            missing_order_ids.add(int(order_id))
            row = order_map[order_id]
            details.append(
                {
                    "order_id": int(order_id),
                    "order_no": _order_display_number(row),
                    "order_item_id": None,
                    "sku": "",
                    "reason": "没有商品明细",
                }
            )
    skipped_rows = [row for row in rows if row.id in missing_order_ids]
    purchasable_rows = [row for row in rows if row.id not in missing_order_ids]
    return purchasable_rows, skipped_rows, details


def _notify_missing_product_names(
    db: Session,
    task: ScheduledTask,
    run: ScheduledTaskRun,
    *,
    skipped_rows: list[Order],
    details: list[dict],
) -> tuple[bool, str]:
    if not skipped_rows:
        return False, "没有缺少中文名称的订单"
    settings = task.settings if isinstance(task.settings, dict) else {}
    recipients = parse_recipients(str(settings.get("failure_email_recipients") or ""))
    if not recipients:
        return False, "未配置收件人"
    subject = f"[CaifuClaw AI] 采购单生成已跳过缺少中文名称的订单：{task.name}"
    detail_lines = [
        f"- {item.get('order_no') or item.get('order_id')}，SKU: {item.get('sku') or '-'}，原因: {item.get('reason') or '产品中文名称为空'}"
        for item in details[:80]
    ]
    if len(details) > 80:
        detail_lines.append(f"- 其余 {len(details) - 80} 条请登录后台查看")
    body = "\n".join(
        [
            "定时任务生成采购单前发现部分订单商品缺少中文名称，系统已跳过这些订单，其余订单继续生成采购单。",
            "",
            f"任务名称：{task.name}",
            f"运行ID：{run.id}",
            f"跳过订单数：{len(skipped_rows)}",
            "",
            "明细：",
            *detail_lines,
            "",
            "请维护产品 SKU 映射和中文名称后，再重新处理这些待采购订单。",
        ]
    )
    try:
        send_email(get_email_setting(db), recipients, subject, body)
        return True, "缺少中文名称通知邮件已发送"
    except Exception as exc:
        return False, f"缺少中文名称通知邮件发送失败：{exc}"


def _order_logistics_age_anchor(row: Order) -> datetime | None:
    return row.created_at or row.payment_at or row.platform_created_at or row.updated_at


def _logistics_timeout_notice_event_key(row: Order) -> str:
    return f"logistics-timeout-24h:{row.id}"


def _has_logistics_timeout_notice(db: Session, row: Order) -> bool:
    if not hasattr(db, "scalar"):
        return False
    return bool(
        db.scalar(
            select(OrderOperationLog.id)
            .where(OrderOperationLog.event_key == _logistics_timeout_notice_event_key(row))
            .limit(1)
        )
    )


def _notify_stale_logistics_pending_orders(
    db: Session,
    task: ScheduledTask,
    rows: list[Order],
) -> tuple[int, str]:
    threshold = _utc_now() - LOGISTICS_STALE_NOTIFY_AFTER
    stale_rows: list[Order] = []
    for row in rows:
        if order_is_overseas_warehouse(row):
            continue
        anchor = _order_logistics_age_anchor(row)
        if anchor and anchor <= threshold and not _has_logistics_timeout_notice(db, row):
            stale_rows.append(row)
    if not stale_rows:
        return 0, "没有超过24小时仍未就绪的订单"

    settings = task.settings if isinstance(task.settings, dict) else {}
    recipients = parse_recipients(str(settings.get("failure_email_recipients") or ""))
    if not recipients:
        return 0, "未配置收件人"

    lines = []
    for row in stale_rows[:80]:
        tracking_state = "已有货运单号" if _order_tracking_number(db, row) else "缺少货运单号"
        lines.append(f"- {_order_display_number(row)}，{tracking_state}，状态：{row.biz_status or '-'}")
    if len(stale_rows) > 80:
        lines.append(f"- 其余 {len(stale_rows) - 80} 条请登录后台查看")
    subject = f"[CaifuClaw AI] 超过24小时未获取完整物流/面单：{task.name}"
    body = "\n".join(
        [
            "以下订单超过24小时仍未同时获取货运单号和真实面单，已暂缓自动打印和采购。",
            "",
            f"任务名称：{task.name}",
            f"订单数：{len(stale_rows)}",
            "",
            "订单：",
            *lines,
            "",
            "请检查平台发货、物流接口或面单获取情况。",
        ]
    )
    try:
        send_email(get_email_setting(db), recipients, subject, body)
    except Exception as exc:
        return 0, f"24小时物流/面单超时通知邮件发送失败：{exc}"
    now = _utc_now()
    for row in stale_rows:
        add_order_operation_log(
            db,
            order_id=row.id,
            operation_type="logistics_timeout_notice",
            operation_attribute="物流面单超时通知",
            description=(
                f"定时任务：订单 {_order_display_number(row)} 超过24小时仍未同时获取货运单号和真实面单，"
                "已发送邮件通知"
            ),
            operator=SYSTEM_OPERATOR,
            source=ORDER_LOG_SYSTEM_SOURCE,
            operated_at=now,
            event_key=_logistics_timeout_notice_event_key(row),
            extra={"task_id": task.id, "threshold_hours": 24},
        )
    if hasattr(db, "commit"):
        db.commit()
    return len(stale_rows), f"已发送24小时物流/面单超时通知 {len(stale_rows)} 条"


def _generate_purchase_and_move_to_picking(
    db: Session,
    task: ScheduledTask,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> PurchaseOrder | None:
    if not rows:
        return None

    input_order_ids = sorted({row.id for row in rows})
    rows_to_waiting_purchase = [row for row in rows if row.biz_status == ORDER_STATUS_WAITING_PRINT]
    if rows_to_waiting_purchase:
        _move_to_waiting_purchase(db, rows_to_waiting_purchase)
    stats["waiting_purchase_count"] = len(rows)
    for row in rows:
        _upsert_run_order(db, run.id, row, status_after=row.biz_status or "")

    step = _start_step(db, run.id, STEP_FILTER_PURCHASE_ORDERS, "过滤缺少中文名称订单", {"order_ids": input_order_ids})
    purchasable_rows, skipped_rows, missing_details = _purchase_missing_product_name_rows(db, rows)
    stats["missing_product_name_count"] = len(skipped_rows)
    notify_message = ""
    if skipped_rows:
        for row in skipped_rows:
            _upsert_run_order(
                db,
                run.id,
                row,
                status_after=row.biz_status or "",
                error_message="采购单生成已跳过：存在产品中文名称为空的明细",
                needs_reprint=False,
            )
        _notified, notify_message = _notify_missing_product_names(
            db,
            task,
            run,
            skipped_rows=skipped_rows,
            details=missing_details,
        )
    filter_message = (
        f"采购前过滤完成，可生成 {len(purchasable_rows)} 单，"
        f"跳过缺少中文名称 {len(skipped_rows)} 单"
    )
    if notify_message:
        filter_message = f"{filter_message}；{notify_message}"
    _finish_step(
        db,
        step,
        status="success",
        message=filter_message,
        stats={
            "input_count": len(rows),
            "purchasable_count": len(purchasable_rows),
            "skipped_count": len(skipped_rows),
            "missing_details": missing_details[:100],
        },
    )
    if not purchasable_rows:
        return None

    order_ids = sorted({row.id for row in purchasable_rows})
    step = _start_step(db, run.id, STEP_GENERATE_PURCHASE_ORDER, "生成采购单", {"order_ids": order_ids})
    waiting_purchase_rows = db.scalars(select(Order).where(Order.id.in_(order_ids)).order_by(asc(Order.id))).all()
    purchase = _generate_purchase_order_for_orders(db, waiting_purchase_rows)
    stats["purchase_order_id"] = purchase.id
    stats["purchase_no"] = purchase.purchase_no
    for row in waiting_purchase_rows:
        _upsert_run_order(db, run.id, row, purchase_order_id=purchase.id)
    _finish_step(
        db,
        step,
        status="success",
        message=f"已生成采购单 {purchase.purchase_no}",
        stats={
            "waiting_purchase_count": len(waiting_purchase_rows),
            "purchase_order_id": purchase.id,
            "purchase_no": purchase.purchase_no,
        },
    )

    step = _start_step(db, run.id, STEP_MOVE_TO_PICKING, "转入配货中", {"order_ids": order_ids, "purchase_order_id": purchase.id})
    _move_to_picking_after_purchase(db, waiting_purchase_rows, purchase)
    stats["picking_count"] = len(waiting_purchase_rows)
    for row in waiting_purchase_rows:
        _upsert_run_order(db, run.id, row, status_after=row.biz_status or "", purchase_order_id=purchase.id)
    _finish_step(
        db,
        step,
        status="success",
        message=f"已转入配货中 {len(waiting_purchase_rows)} 条",
        stats={"picking_count": len(waiting_purchase_rows), "purchase_order_id": purchase.id, "purchase_no": purchase.purchase_no},
    )
    return purchase


def _move_overseas_warehouse_to_shipped(
    db: Session,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> None:
    if not rows:
        return
    now = _utc_now()
    status_before = {row.id: row.biz_status or "" for row in rows}
    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = "shipped"
        if row.label_printed_at is None:
            row.label_printed_at = now
        if getattr(row, "shipped_at", None) is None:
            row.shipped_at = now
        if getattr(row, "marked_shipped_at", None) is None:
            row.marked_shipped_at = now
        row.updated_at = now
        _upsert_run_order(
            db,
            run.id,
            row,
            status_before=status_before.get(row.id, ""),
            status_after=row.biz_status or "",
            print_submitted=False,
            print_message="海外仓订单无需平台面单和采购，已转为已发货",
            pdf_generated=False,
            needs_reprint=False,
        )
    stats["overseas_warehouse_skipped_count"] = int(stats.get("overseas_warehouse_skipped_count", 0) or 0) + len(rows)
    stats["shipped_count"] = int(stats.get("shipped_count", 0) or 0) + len(rows)
    add_order_operation_logs(
        db,
        rows,
        operation_type="sync_logistics",
        operation_attribute="同步物流信息",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 为海外仓订单，无需同步物流、面单和采购，"
            f"状态：{ORDER_STATUS_PENDING} -> {ORDER_STATUS_SHIPPED}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra={"skipped_reason": "overseas_warehouse", "run_id": run.id},
    )
    db.commit()


def _record_bsi_draft_created(
    db: Session,
    run: ScheduledTaskRun,
    group: BsiDraftGroupResult,
    stats: dict,
) -> None:
    rows = group.rows
    if not rows:
        return
    now = _utc_now()
    status_before = {row.id: row.biz_status or "" for row in rows}
    for row in rows:
        if group.provider_order_no:
            row.bsi_order_no = group.provider_order_no
            if not getattr(row, "bsi_submitted_at", None):
                row.bsi_submitted_at = now
        _upsert_run_order(
            db,
            run.id,
            row,
            status_before=status_before.get(row.id, ""),
            status_after=row.biz_status or "",
            print_submitted=False,
            print_message=(
                f"BSI 备货草稿已存在，跳过重复提交：{group.provider_order_no}"
                if group.reused
                else f"BSI 备货草稿已记录：{group.provider_order_no}"
            ),
            pdf_generated=False,
            needs_reprint=False,
            error_message=getattr(row, "error_message", "") or "",
        )
    stat_key = "bsi_draft_reused_count" if group.reused else "bsi_draft_succeeded_count"
    stats[stat_key] = int(stats.get(stat_key, 0) or 0) + 1
    stats["bsi_draft_logged_count"] = int(stats.get("bsi_draft_logged_count", 0) or 0) + len(rows)
    add_order_operation_logs(
        db,
        rows,
        operation_type="bsi_draft_skipped" if group.reused else "bsi_draft_created",
        operation_attribute="复用BSI备货订单" if group.reused else "创建BSI备货订单",
        description=lambda order: (
            f"定时任务：{order.platform} BSI海外仓订单 {_order_display_number(order)} "
            + (
                f"已有 BSI 草稿 {group.provider_order_no}，跳过重复提交"
                if group.reused
                else f"已创建备货草稿 {group.provider_order_no}"
            )
            + "，已记录 BSI 单号，不改变订单状态；待Order follow up登记成功后转为已发货"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra={
            "provider_order_no": group.provider_order_no,
            "draft_status": 2,
            "reused": group.reused,
            "run_id": run.id,
        },
    )
    db.commit()


def _record_joom_bsi_draft_created(
    db: Session,
    run: ScheduledTaskRun,
    group: BsiDraftGroupResult,
    stats: dict,
) -> None:
    """Backward-compatible alias for scheduled-task extensions."""
    _record_bsi_draft_created(db, run, group, stats)


def _queue_joom_fbj_follow_up_export(
    db: Session,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> None:
    if not rows:
        return
    now = _utc_now()
    status_before = {row.id: row.biz_status or "" for row in rows}
    for row in rows:
        row.local_status = "fbj_follow_up_pending"
        row.error_message = ""
        row.updated_at = now
        _upsert_run_order(
            db,
            run.id,
            row,
            status_before=status_before.get(row.id, ""),
            status_after=row.biz_status,
            print_submitted=False,
            print_message="FBJ订单登记跟进表，不获取平台面单、不打印、不生成采购单",
            pdf_generated=False,
            needs_reprint=False,
        )
    stats["joom_fbj_follow_up_export_count"] = int(stats.get("joom_fbj_follow_up_export_count", 0) or 0) + len(rows)
    add_order_operation_logs(
        db,
        rows,
        operation_type="fbj_follow_up_export_queued",
        operation_attribute="FBJ订单登记跟进表",
        description=lambda order: (
            f"定时任务：Joom FBJ订单 {_order_display_number(order)} 保持待处理，"
            "登记跟进表且不获取平台面单、不打印、不生成采购单"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra=lambda order: {
            "run_id": run.id,
            "status_before": status_before.get(order.id, ""),
            "status_after": order.biz_status or "",
        },
    )
    db.commit()


def _move_logistics_label_exempt_to_shipped(
    db: Session,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> None:
    if not rows:
        return
    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = "shipped"
        if row.label_printed_at is None:
            row.label_printed_at = now
        if getattr(row, "shipped_at", None) is None:
            row.shipped_at = now
        if getattr(row, "marked_shipped_at", None) is None:
            row.marked_shipped_at = now
        row.updated_at = now
        _upsert_run_order(
            db,
            run.id,
            row,
            status_after=row.biz_status or "",
            print_submitted=False,
            print_message="该订单无需获取平台货运单号、面单和采购，已转为已发货",
            pdf_generated=False,
            needs_reprint=False,
        )
    stats["logistics_label_exempt_skipped_count"] = int(stats.get("logistics_label_exempt_skipped_count", 0) or 0) + len(rows)
    stats["shipped_count"] = int(stats.get("shipped_count", 0) or 0) + len(rows)
    add_order_operation_logs(
        db,
        rows,
        operation_type="sync_logistics",
        operation_attribute="同步物流信息",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 无需获取平台货运单号、面单和采购，"
            f"状态：{ORDER_STATUS_PENDING} -> {ORDER_STATUS_SHIPPED}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra={"skipped_reason": "logistics_label_exempt", "run_id": run.id},
    )
    db.commit()


def _move_delivered_without_label_to_shipped(
    db: Session,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> None:
    if not rows:
        return
    now = _utc_now()
    status_before = {row.id: row.biz_status or "" for row in rows}
    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = "shipped"
        row.shipped_at = row.shipped_at or row.handover_at or now
        row.marked_shipped_at = row.marked_shipped_at or now
        row.error_message = ""
        row.updated_at = now
        _upsert_run_order(
            db,
            run.id,
            row,
            status_before=status_before.get(row.id, ""),
            status_after=row.biz_status or "",
            print_submitted=False,
            print_message="MercadoLibre订单已妥投且无法再下载真实面单，跳过打印、采购和配货并转为已发货",
            pdf_generated=False,
            needs_reprint=False,
            error_message="",
        )
    stats["delivered_without_label_shipped_count"] = (
        int(stats.get("delivered_without_label_shipped_count", 0) or 0) + len(rows)
    )
    stats["shipped_count"] = int(stats.get("shipped_count", 0) or 0) + len(rows)
    add_order_operation_logs(
        db,
        rows,
        operation_type="platform_delivered_auto_shipped",
        operation_attribute="同步物流信息",
        description=lambda order: (
            f"定时任务：MercadoLibre订单 {_order_display_number(order)} 平台状态已为 delivered，"
            "已有货运单号但平台无法再提供真实面单，已跳过打印、采购和配货并转为已发货"
            + _order_tracking_log_suffix(db, order)
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra=lambda order: {
            "skipped_reason": "platform_delivered_without_label",
            "run_id": run.id,
            "platform_status": str(getattr(order, "platform_status", "") or ""),
            "tracking_number": _order_tracking_number_value(db, order),
        },
    )
    db.commit()


def _move_joom_offline_shipping_to_shipped(
    db: Session,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> None:
    if not rows:
        return
    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = "shipped"
        row.shipped_at = row.shipped_at or row.handover_at or now
        row.error_message = ""
        row.updated_at = now
        _upsert_run_order(
            db,
            run.id,
            row,
            status_after=row.biz_status or "",
            print_submitted=False,
            print_message="Joom 线下物流订单已由平台发货，跳过在线面单、打印和采购",
            pdf_generated=False,
            needs_reprint=False,
            error_message="",
        )
    stats["joom_offline_shipped_count"] = int(stats.get("joom_offline_shipped_count", 0) or 0) + len(rows)
    stats["shipped_count"] = int(stats.get("shipped_count", 0) or 0) + len(rows)
    add_order_operation_logs(
        db,
        rows,
        operation_type="joom_offline_shipped",
        operation_attribute="Joom线下物流",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 为 Joom 线下物流订单，平台已发货，"
            "已跳过在线面单、打印和采购"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra={"skipped_reason": "joom_offline_shipping", "run_id": run.id},
    )
    db.commit()


def _move_logistics_rule_unmatched_to_shipped(
    db: Session,
    run: ScheduledTaskRun,
    rows: list[Order],
    stats: dict,
) -> None:
    if not rows:
        return
    from .main import _mark_logistics_rule_unmatched_as_shipped

    now = _utc_now()
    _mark_logistics_rule_unmatched_as_shipped(
        db,
        rows,
        SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        extra={"run_id": run.id},
    )
    for row in rows:
        _upsert_run_order(
            db,
            run.id,
            row,
            status_after=row.biz_status or "",
            print_submitted=False,
            print_message="物流规则未匹配，跳过同步物流、打印和采购",
            pdf_generated=False,
            needs_reprint=False,
        )
    stats["logistics_rule_unmatched_shipped_count"] = int(stats.get("logistics_rule_unmatched_shipped_count", 0) or 0) + len(rows)
    stats["shipped_count"] = int(stats.get("shipped_count", 0) or 0) + len(rows)
    db.commit()


def _backup_merged_pdf(platform: str, run_id: int, pdf_bytes: bytes) -> str:
    file_path, _sha256 = save_label_pdf("system", "scheduled-task", platform or "unknown", f"run-{run_id}", pdf_bytes)
    return file_path


def _merge_pdf_parts(parts: list[bytes]) -> bytes:
    return merge_pdf_parts(parts)


def _print_setting_page_orientation(platform: str, print_setting: PlatformPrintSetting | None) -> str:
    return label_orientation_for_platform(
        platform,
        getattr(print_setting, "page_orientation", None) if print_setting else None,
    )


def _missing_print_settings(platforms: list[str], printer_map: dict[str, PlatformPrintSetting]) -> list[str]:
    return [platform for platform in platforms if not (getattr(printer_map.get(platform), "printer_name", "") or "").strip()]


def _should_require_chinese_label_setting(db: Session) -> bool:
    return all(hasattr(db, name) for name in ("scalar", "add", "flush", "commit", "refresh"))


def _ordered_platforms_for_print(
    waiting_print_rows: list[Order],
    printer_map: dict[str, PlatformPrintSetting],
) -> list[str]:
    platforms: list[str] = []
    row_platforms = []
    for row in waiting_print_rows:
        platform = row.platform or ""
        row_platforms.append(platform)
    row_platform_set = set(row_platforms)
    printer_order: list[str] = []
    printer_groups: dict[str, list[str]] = {}
    for platform_key, setting in printer_map.items():
        platform = getattr(setting, "platform", None) or platform_key or ""
        if platform == PRINT_PLATFORM_CHINESE_LABEL or platform not in row_platform_set or platform in platforms:
            continue
        printer_name = (setting.printer_name or "").strip()
        if printer_name not in printer_groups:
            printer_order.append(printer_name)
            printer_groups[printer_name] = []
        printer_groups[printer_name].append(platform)
    for printer_name in printer_order:
        platforms.extend(printer_groups[printer_name])
    for platform in row_platforms:
        if platform not in platforms:
            platforms.append(platform)
    return platforms


def _submit_pdf_to_printer_windows(
    pdf_path: str,
    printer_name: str,
    *,
    allow_offline_queue: bool = False,
    require_queue_observed: bool = False,
    job_name: str | None = None,
    page_orientation: str | None = PRINT_ORIENTATION_AUTO,
    target_size_mm: tuple[float, float] | None = None,
) -> tuple[bool, str]:
    if not printer_name:
        return False, "未配置打印机名称"
    configured_printer_name = printer_name
    lookup_detail = _printer_lookup_detail(configured_printer_name, printer_name)

    printer_name_ps = _ps_quote(printer_name)
    printer_probe = _run_powershell(
        f"$p = Get-Printer -Name '{printer_name_ps}' -ErrorAction SilentlyContinue; "
        f"if ($null -eq $p) {{ exit 2 }}; "
        f"$c = Get-CimInstance Win32_Printer | Where-Object {{ $_.Name -eq '{printer_name_ps}' }} | Select-Object -First 1; "
        f"if (($p.PrinterStatus -eq 'Offline') -or ($p.WorkOffline -eq $true) -or ($null -ne $c -and $c.WorkOffline -eq $true)) {{ exit 3 }}; "
        f"exit 0",
        timeout=20,
    )
    if printer_probe is None:
        return False, "Windows PowerShell 不可用，无法检查打印机"
    if printer_probe.returncode == 2:
        return False, f"打印机不存在: {configured_printer_name}"
    printer_is_offline = printer_probe.returncode == 3
    if printer_is_offline and not allow_offline_queue:
        return False, f"打印机离线: {printer_name}{lookup_detail}"
    if printer_probe.returncode != 0 and not printer_is_offline:
        message = printer_probe.stderr.strip() or printer_probe.stdout.strip() or "unknown"
        return False, f"打印机检查失败: {message}"

    document_name = _safe_print_job_name(job_name or Path(pdf_path).name)
    if not document_name.lower().endswith(".pdf"):
        document_name = f"{document_name}.pdf"
    cleanup_path: str | None = None
    try:
        printable_pdf_path, cleanup_path = _orientation_adjusted_pdf_path(pdf_path, page_orientation, target_size_mm)
        submitted, message = _submit_pdf_to_printer_gdi(
            printable_pdf_path,
            printer_name,
            document_name,
            page_orientation=page_orientation,
        )
        if not submitted:
            return False, message
        if require_queue_observed:
            for _ in range(8):
                snapshot = _print_queue_snapshot(printer_name, document_name)
                if int(snapshot.get("job_count") or 0) > 0:
                    suffix = "（打印机当前脱机，已进入队列）" if printer_is_offline else ""
                    return True, f"{message}{lookup_detail}{suffix}"
                time.sleep(1)
            return True, f"{message}{lookup_detail}（已提交但未检测到队列任务，需人工确认）"
        suffix = "（打印机当前脱机，已进入队列）" if printer_is_offline else ""
        return True, f"{message}{lookup_detail}{suffix}"
    finally:
        if cleanup_path:
            try:
                Path(cleanup_path).unlink(missing_ok=True)
            except Exception:
                pass


def _submit_pdf_to_printer_cups(
    pdf_path: str,
    printer_name: str,
    *,
    allow_offline_queue: bool = False,
    require_queue_observed: bool = False,
    job_name: str | None = None,
    page_orientation: str | None = PRINT_ORIENTATION_AUTO,
    target_size_mm: tuple[float, float] | None = None,
) -> tuple[bool, str]:
    if not printer_name:
        return False, "未配置打印机名称"
    lp = _cups_command("lp")
    if not lp:
        return False, "CUPS 打印命令 lp 不可用，无法提交打印"
    lpstat = _cups_command("lpstat")
    configured_printer_name = printer_name
    lookup_detail = _printer_lookup_detail(configured_printer_name, printer_name)

    document_name = _safe_print_job_name(job_name or Path(pdf_path).name)
    if not document_name.lower().endswith(".pdf"):
        document_name = f"{document_name}.pdf"
    snapshot = _print_queue_snapshot_cups(printer_name)
    if not snapshot.get("exists"):
        return False, f"打印机不存在: {configured_printer_name}"
    printer_is_offline = bool(snapshot.get("offline"))
    if printer_is_offline and not allow_offline_queue:
        return False, f"打印机离线: {printer_name}{lookup_detail}"

    cleanup_path: str | None = None
    media_name = ""
    try:
        printable_pdf_path, cleanup_path = _orientation_adjusted_pdf_path(pdf_path, page_orientation, target_size_mm)
        lp_args = [lp, "-d", printer_name, "-t", document_name]
        media_options = _cups_media_options(printable_pdf_path, target_size_mm)
        media_name = next((value.removeprefix("media=") for value in media_options if value.startswith("media=")), "")
        lp_args.extend(media_options)
        lp_args.append(printable_pdf_path)
        submit_result = subprocess.run(
            lp_args,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return False, f"提交打印失败: {exc}"
    finally:
        if cleanup_path:
            try:
                Path(cleanup_path).unlink(missing_ok=True)
            except Exception:
                pass
    if submit_result.returncode != 0:
        message = (submit_result.stderr or submit_result.stdout or "unknown").strip()
        return False, f"提交打印失败: {message}"

    output = (submit_result.stdout or submit_result.stderr or "").strip()
    queue_verified = not require_queue_observed
    if require_queue_observed:
        for _ in range(8):
            observed = _print_queue_snapshot_cups(printer_name, document_name)
            if int(observed.get("job_count") or 0) > 0:
                queue_verified = True
                break
            time.sleep(1)
        if not queue_verified and printer_is_offline:
            queue_verified = False

    suffix = "（打印机当前脱机，已进入队列）" if printer_is_offline else ""
    if require_queue_observed and not queue_verified:
        suffix += "（已提交但未检测到队列任务，需人工确认）"
    media_detail = f"，纸张: {media_name}" if media_name else ""
    detail = f"，{output}" if output else ""
    return True, f"已提交打印队列: {printer_name}，任务名: {document_name}{media_detail}{detail}{lookup_detail}{suffix}"


def _submit_pdf_to_printer(
    pdf_path: str,
    printer_name: str,
    *,
    allow_offline_queue: bool = False,
    require_queue_observed: bool = False,
    job_name: str | None = None,
    page_orientation: str | None = PRINT_ORIENTATION_AUTO,
    target_size_mm: tuple[float, float] | None = None,
) -> tuple[bool, str]:
    if _is_windows():
        return _submit_pdf_to_printer_windows(
            pdf_path,
            printer_name,
            allow_offline_queue=allow_offline_queue,
            require_queue_observed=require_queue_observed,
            job_name=job_name,
            page_orientation=page_orientation,
            target_size_mm=target_size_mm,
        )
    return _submit_pdf_to_printer_cups(
        pdf_path,
        printer_name,
        allow_offline_queue=allow_offline_queue,
        require_queue_observed=require_queue_observed,
        job_name=job_name,
        page_orientation=page_orientation,
        target_size_mm=target_size_mm,
    )


def _print_needs_manual_confirmation(message: str) -> bool:
    text = (message or "").lower()
    return "需人工确认" in message or "未检测到队列任务" in message or "无法确认" in message or "cannot confirm" in text


def _notify_uncertain_prints(
    db: Session,
    task: ScheduledTask,
    run: ScheduledTaskRun,
    *,
    printer_name: str,
    platform: str,
    rows: list[Order],
    pdf_path: str,
    print_message: str,
) -> tuple[bool, str]:
    settings = task.settings if isinstance(task.settings, dict) else {}
    recipients = parse_recipients(str(settings.get("failure_email_recipients") or ""))
    if not recipients:
        return False, "未配置收件人"

    labels = [
        row.shipment_tracking_number
        or row.platform_order_no
        or row.posting_number
        or row.platform_order_id
        or str(row.id)
        for row in rows
    ]
    subject = f"[CaifuClaw AI] 打印结果需人工确认：{task.name}"
    body = "\n".join(
        [
            "系统已向打印机提交面单，但无法确认是否已经实际打印。",
            "",
            f"任务名称：{task.name}",
            f"运行ID：{run.id}",
            f"平台：{platform or 'unknown'}",
            f"打印机：{printer_name or '-'}",
            f"订单数：{len(rows)}",
            f"打印消息：{print_message or '-'}",
            "",
            "涉及订单/货运单号：",
            *[f"- {label}" for label in labels[:50]],
            *(([f"- 其余 {len(labels) - 50} 条请登录后台查看"] if len(labels) > 50 else [])),
            "",
            "请人工检查打印机出纸情况；如未打印，请在任务日志中手动重打对应 PDF。",
        ]
    )
    attachments: list[EmailAttachment] = []
    try:
        path = Path(pdf_path)
        if path.is_file() and path.suffix.lower() == ".pdf":
            attachments.append(EmailAttachment(filename=path.name, content=path.read_bytes()))
    except OSError:
        attachments = []
    try:
        send_email(get_email_setting(db), recipients, subject, body, attachments=attachments)
        return True, f"已发送人工确认邮件，附件 {len(attachments)} 个"
    except Exception as exc:
        return False, f"人工确认邮件发送失败：{exc}"


def _mark_orders_shipped(db: Session, rows: list[Order]) -> None:
    now = _utc_now()
    for row in rows:
        row.biz_status = ORDER_STATUS_SHIPPED
        row.local_status = "shipped"
        row.shipped_at = now
        row.marked_shipped_at = now
        shipment = _latest_shipment(db, row.id)
        if shipment and not row.shipment_tracking_number:
            row.shipment_tracking_number = shipment.tracking_number
        if shipment and not row.handover_at:
            row.handover_at = shipment.created_at
        row.updated_at = now
    add_order_operation_logs(
        db,
        rows,
        operation_type="mark_shipped",
        operation_attribute="修改订单基础信息",
        description=lambda order: (
            f"定时任务：订单 {_order_display_number(order)} 已标记发货，"
            f"状态：{ORDER_STATUS_PICKING} -> {ORDER_STATUS_SHIPPED}"
            + _order_tracking_log_suffix(db, order)
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
    )
    db.commit()


async def _auto_order_pipeline_async(db: Session, task: ScheduledTask, run: ScheduledTaskRun) -> tuple[str, str, dict]:
    stats = {
        "selected_orders": 0,
        "logistics_submitted": 0,
        "logistics_ready_count": 0,
        "label_pending_count": 0,
        "waiting_print_count": 0,
        "tracking_ready_count": 0,
        "tracking_pending_count": 0,
        "pdf_platform_count": 0,
        "pdf_platforms": [],
        "pdf_success_count": 0,
        "chinese_label_pdf_generated": False,
        "chinese_label_print_success_count": 0,
        "chinese_label_print_failed_count": 0,
        "print_success_count": 0,
        "print_failed_count": 0,
        "print_uncertain_count": 0,
        "waiting_purchase_count": 0,
        "missing_product_name_count": 0,
        "purchase_order_id": None,
        "purchase_no": "",
        "picking_count": 0,
        "shipped_count": 0,
        "logistics_wait_timed_out": False,
        "stale_logistics_notice_count": 0,
        "overseas_warehouse_skipped_count": 0,
        "bsi_draft_succeeded_count": 0,
        "bsi_draft_reused_count": 0,
        "bsi_draft_waiting_count": 0,
        "bsi_draft_logged_count": 0,
        "logistics_label_exempt_skipped_count": 0,
        "delivered_without_label_shipped_count": 0,
        "logistics_rule_unmatched_shipped_count": 0,
        "joom_offline_shipped_count": 0,
        "joom_offline_waiting_count": 0,
        "joom_offline_terminal_count": 0,
        "joom_fbj_follow_up_export_count": 0,
        "printer_monitor": [],
        "post_submit_printer_notifications": [],
    }

    step = _start_step(db, run.id, STEP_SYNC_ORDERS, "跳过平台订单同步", {"task_id": task.id})
    _finish_step(
        db,
        step,
        status="success",
        message="已跳过平台接口取数，仅处理系统已有订单",
        stats={"skipped": True, "source": "existing_orders"},
    )

    pending_rows, _retry_resume = _select_orders_for_run(db, run)
    if not pending_rows:
        step = _start_step(db, run.id, STEP_SYNC_LOGISTICS, "创建/刷新物流信息", {})
        _finish_step(db, step, status="success", message="没有待处理订单", stats={"selected_orders": 0})
        return "success", "没有待处理订单", stats
    for row in pending_rows:
        _upsert_run_order(db, run.id, row, status_before=row.biz_status or "")
    stats["selected_orders"] = len(pending_rows)

    rules = load_enabled_logistics_rules(db)
    bsi_rows = [
        row
        for row in pending_rows
        if order_has_bsi_draft(row)
        or order_matches_logistics_carrier_rule(row, rules, BSI_CARRIER_CODE)
    ]
    if bsi_rows:
        step = _start_step(
            db,
            run.id,
            STEP_CREATE_BSI_DRAFT,
            "创建BSI备货草稿",
            {"order_ids": [row.id for row in bsi_rows]},
        )
        bsi_result = await process_bsi_drafts(db, bsi_rows)
        for group in bsi_result.groups:
            if group.succeeded:
                _record_bsi_draft_created(db, run, group, stats)
                continue
            for row in group.rows:
                row.error_message = group.message[:1000]
                row.updated_at = _utc_now()
                _upsert_run_order(
                    db,
                    run.id,
                    row,
                    status_after=row.biz_status or "",
                    print_submitted=False,
                    print_message="BSI 备货草稿尚未创建，订单保留待处理",
                    pdf_generated=False,
                    needs_reprint=False,
                    error_message=group.message,
                )
        stats["bsi_draft_waiting_count"] += bsi_result.waiting_group_count
        db.commit()
        _finish_step(
            db,
            step,
            status="success",
            message=(
                f"BSI备货草稿处理完成，成功 {bsi_result.succeeded_group_count} 单，"
                f"保留待处理 {bsi_result.waiting_group_count} 单"
            ),
            stats={
                "succeeded_group_count": bsi_result.succeeded_group_count,
                "waiting_group_count": bsi_result.waiting_group_count,
                "shipped_order_count": len(bsi_result.succeeded_rows),
            },
        )
        bsi_ids = {row.id for row in bsi_rows}
        pending_rows = [row for row in pending_rows if row.id not in bsi_ids]

    fbj_rows = [row for row in pending_rows if order_is_joom_fbj_warehouse(row)]
    if fbj_rows:
        step = _start_step(
            db,
            run.id,
            STEP_QUEUE_JOOM_FBJ_FOLLOW_UP_EXPORT,
            "Joom FBJ订单登记跟进表",
            {"order_ids": [row.id for row in fbj_rows]},
        )
        _queue_joom_fbj_follow_up_export(db, run, fbj_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"Joom FBJ订单已登记跟进表 {len(fbj_rows)} 条，保持待处理且不进入面单、打印和采购流程",
            stats={"queued_count": len(fbj_rows)},
        )
    if fbj_rows:
        fbj_ids = {row.id for row in fbj_rows}
        pending_rows = [row for row in pending_rows if row.id not in fbj_ids]

    overseas_rows = [row for row in pending_rows if order_is_overseas_warehouse(row)]
    if overseas_rows:
        step = _start_step(
            db,
            run.id,
            STEP_SKIP_OVERSEAS_WAREHOUSE,
            "海外仓跳过物流、面单和采购",
            {"order_ids": [row.id for row in overseas_rows]},
        )
        _move_overseas_warehouse_to_shipped(db, run, overseas_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"海外仓订单无需同步物流、面单和采购，已转为已发货 {len(overseas_rows)} 条",
            stats={"skipped_count": len(overseas_rows)},
        )
        overseas_ids = {row.id for row in overseas_rows}
        pending_rows = [row for row in pending_rows if row.id not in overseas_ids]

    joom_offline_rows = [row for row in pending_rows if order_is_joom_offline_shipping(row)]
    if joom_offline_rows:
        step = _start_step(
            db,
            run.id,
            STEP_HANDLE_JOOM_OFFLINE_SHIPPING,
            "处理Joom线下物流",
            {"order_ids": [row.id for row in joom_offline_rows]},
        )
        refresh_stats = await refresh_order_logistics_for_rows(
            db,
            joom_offline_rows,
            preserve_biz_status=False,
        )
        shipped_rows = [
            row for row in joom_offline_rows if joom_offline_shipping_target_status(row) == ORDER_STATUS_SHIPPED
        ]
        terminal_rows = [
            row
            for row in joom_offline_rows
            if joom_offline_shipping_target_status(row) in {"已妥投", "已完成", "已作废"}
        ]
        handled_ids = {row.id for row in shipped_rows + terminal_rows}
        waiting_rows = [row for row in joom_offline_rows if row.id not in handled_ids]
        _move_joom_offline_shipping_to_shipped(db, run, shipped_rows, stats)
        for row in terminal_rows:
            _upsert_run_order(db, run.id, row, status_after=row.biz_status or "", error_message="")
        for row in waiting_rows:
            _upsert_run_order(
                db,
                run.id,
                row,
                status_after=row.biz_status or "",
                error_message="Joom 线下物流订单尚未返回已发货状态和货运单号，等待平台状态更新",
                needs_reprint=False,
            )
        stats["joom_offline_waiting_count"] += len(waiting_rows)
        stats["joom_offline_terminal_count"] += len(terminal_rows)
        _finish_step(
            db,
            step,
            status="success",
            message=(
                f"Joom 线下物流处理完成，已发货 {len(shipped_rows)} 条，"
                f"其他终态 {len(terminal_rows)} 条，等待平台发货 {len(waiting_rows)} 条"
            ),
            stats={
                "shipped_count": len(shipped_rows),
                "terminal_count": len(terminal_rows),
                "waiting_count": len(waiting_rows),
                "refresh": refresh_stats,
            },
        )
        joom_offline_ids = {row.id for row in joom_offline_rows}
        pending_rows = [row for row in pending_rows if row.id not in joom_offline_ids]

    waiting_purchase_rows = [row for row in pending_rows if row.biz_status == ORDER_STATUS_WAITING_PURCHASE]
    waiting_purchase_label_exempt_rows = [row for row in waiting_purchase_rows if order_is_overseas_warehouse(row)]
    waiting_purchase_label_exempt_ids = {row.id for row in waiting_purchase_label_exempt_rows}
    waiting_purchase_logistics_exempt_rows = [
        row
        for row in waiting_purchase_rows
        if row.id not in waiting_purchase_label_exempt_ids and order_is_logistics_label_exempt(row)
    ]
    if waiting_purchase_label_exempt_rows:
        step = _start_step(
            db,
            run.id,
            STEP_SKIP_OVERSEAS_WAREHOUSE,
            "待采购海外仓跳过采购",
            {"order_ids": [row.id for row in waiting_purchase_label_exempt_rows]},
        )
        _move_overseas_warehouse_to_shipped(db, run, waiting_purchase_label_exempt_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"待采购海外仓订单无需采购，已转为已发货 {len(waiting_purchase_label_exempt_rows)} 条",
            stats={"skipped_count": len(waiting_purchase_label_exempt_rows)},
        )
    if waiting_purchase_logistics_exempt_rows:
        step = _start_step(
            db,
            run.id,
            STEP_SKIP_LOGISTICS_LABEL_EXEMPT,
            "待采购免面单跳过采购",
            {"order_ids": [row.id for row in waiting_purchase_logistics_exempt_rows]},
        )
        _move_logistics_label_exempt_to_shipped(db, run, waiting_purchase_logistics_exempt_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"待采购免面单订单无需采购，已转为已发货 {len(waiting_purchase_logistics_exempt_rows)} 条",
            stats={"skipped_count": len(waiting_purchase_logistics_exempt_rows)},
        )
    waiting_purchase_exempt_ids = waiting_purchase_label_exempt_ids | {row.id for row in waiting_purchase_logistics_exempt_rows}
    purchase_ready_order_ids: set[int] = {
        row.id
        for row in waiting_purchase_rows
        if row.id not in waiting_purchase_exempt_ids
    }
    logistics_candidate_rows = [
        row
        for row in pending_rows
        if row.biz_status in {ORDER_STATUS_PENDING, ORDER_STATUS_WAITING_PRINT}
    ]
    rules = load_enabled_logistics_rules(db)
    logistics_candidate_rows, unmatched_rule_rows = split_logistics_rule_eligible_orders(
        logistics_candidate_rows,
        rules,
        matched_at=_utc_now(),
    )
    if unmatched_rule_rows:
        step = _start_step(
            db,
            run.id,
            STEP_MARK_SHIPPED,
            "物流规则未匹配转已发货",
            {"order_ids": [row.id for row in unmatched_rule_rows]},
        )
        _move_logistics_rule_unmatched_to_shipped(db, run, unmatched_rule_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"平台已启用物流规则但未匹配，已跳过物流、打印和采购并转已发货 {len(unmatched_rule_rows)} 条",
            stats={"shipped_count": len(unmatched_rule_rows)},
        )
    overseas_candidate_rows = [row for row in logistics_candidate_rows if order_is_overseas_warehouse(row)]
    if overseas_candidate_rows:
        step = _start_step(
            db,
            run.id,
            STEP_SKIP_OVERSEAS_WAREHOUSE,
            "海外仓跳过物流、面单和采购",
            {"order_ids": [row.id for row in overseas_candidate_rows]},
        )
        _move_overseas_warehouse_to_shipped(db, run, overseas_candidate_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"海外仓订单无需同步物流、面单和采购，已转为已发货 {len(overseas_candidate_rows)} 条",
            stats={"skipped_count": len(overseas_candidate_rows)},
        )
    overseas_candidate_ids = {row.id for row in overseas_candidate_rows}
    logistics_candidate_rows = [row for row in logistics_candidate_rows if row.id not in overseas_candidate_ids]
    exempt_candidate_rows = [row for row in logistics_candidate_rows if order_is_logistics_label_exempt(row)]
    if exempt_candidate_rows:
        step = _start_step(
            db,
            run.id,
            STEP_SKIP_LOGISTICS_LABEL_EXEMPT,
            "跳过平台物流、面单和采购",
            {"order_ids": [row.id for row in exempt_candidate_rows]},
        )
        _move_logistics_label_exempt_to_shipped(db, run, exempt_candidate_rows, stats)
        _finish_step(
            db,
            step,
            status="success",
            message=f"订单无需获取平台货运单号、面单和采购，已转为已发货 {len(exempt_candidate_rows)} 条",
            stats={"skipped_count": len(exempt_candidate_rows)},
        )
    exempt_candidate_ids = {row.id for row in exempt_candidate_rows}
    logistics_candidate_rows = [row for row in logistics_candidate_rows if row.id not in exempt_candidate_ids]

    ready_print_rows: list[Order] = []
    if logistics_candidate_rows:
        step = _start_step(
            db,
            run.id,
            STEP_LOGISTICS_READY_WAIT,
            "同步物流和面单并等待就绪",
            {
                "order_ids": [row.id for row in logistics_candidate_rows],
                "timeout_seconds": _task_logistics_ready_timeout_seconds(task),
                "poll_seconds": _task_logistics_ready_poll_seconds(task),
            },
        )
        ready_print_rows, wait_stats = await _wait_for_logistics_and_labels_ready(
            db,
            task,
            logistics_candidate_rows,
            eligible_statuses={ORDER_STATUS_PENDING, ORDER_STATUS_WAITING_PRINT},
        )
        readiness = wait_stats.get("readiness") or {}
        attempts = wait_stats.get("attempts") or []
        stats["logistics_submitted"] = sum(int((attempt.get("stats") or {}).get("submitted", 0) or 0) for attempt in attempts)
        stats["tracking_ready_count"] = int(readiness.get("tracking_ready_count", 0) or 0)
        stats["tracking_pending_count"] = int(readiness.get("tracking_pending_count", 0) or 0)
        stats["label_pending_count"] = int(readiness.get("label_pending_count", 0) or 0)
        stats["logistics_ready_count"] = len(ready_print_rows)
        stats["logistics_wait_timed_out"] = bool(wait_stats.get("timed_out"))
        delivered_without_label_ids = set(readiness.get("delivered_without_label_order_ids") or [])
        delivered_without_label_rows = [
            row for row in logistics_candidate_rows if row.id in delivered_without_label_ids
        ]
        logistics_message = (
            f"物流/面单同步完成，候选 {len(logistics_candidate_rows)} 条，"
            f"就绪 {len(ready_print_rows)} 条，缺货运单号 {stats['tracking_pending_count']} 条，"
            f"缺面单 {stats['label_pending_count']} 条，平台已妥投且无面单 {len(delivered_without_label_rows)} 条，"
            f"尝试 {len(attempts)} 次，"
            f"等待 {wait_stats.get('waited_seconds', 0)} 秒"
        )
        if stats["logistics_wait_timed_out"]:
            logistics_message += "，已达到等待上限"
        _finish_step(
            db,
            step,
            status="success",
            message=logistics_message,
            stats=wait_stats,
        )

        if delivered_without_label_rows:
            step = _start_step(
                db,
                run.id,
                STEP_MARK_DELIVERED_WITHOUT_LABEL_SHIPPED,
                "平台已妥投且无面单转已发货",
                {"order_ids": [row.id for row in delivered_without_label_rows]},
            )
            _move_delivered_without_label_to_shipped(
                db,
                run,
                delivered_without_label_rows,
                stats,
            )
            _finish_step(
                db,
                step,
                status="success",
                message=(
                    "MercadoLibre订单平台已妥投且无法再下载真实面单，"
                    f"已跳过打印、采购和配货并转为已发货 {len(delivered_without_label_rows)} 条"
                ),
                stats={"shipped_count": len(delivered_without_label_rows)},
            )

        ready_ids = {row.id for row in ready_print_rows}
        handled_ids = ready_ids | delivered_without_label_ids
        not_ready_rows = [row for row in logistics_candidate_rows if row.id not in handled_ids]
        for row in not_ready_rows:
            _upsert_run_order(
                db,
                run.id,
                row,
                error_message="待平台返回货运单号和真实面单，暂不打印",
                needs_reprint=False,
                status_after=row.biz_status or "",
            )
        if not_ready_rows:
            step = _start_step(
                db,
                run.id,
                STEP_NOTIFY_LOGISTICS_TIMEOUT,
                "24小时物流/面单超时通知",
                {"order_ids": [row.id for row in not_ready_rows]},
            )
            notice_count, notice_message = _notify_stale_logistics_pending_orders(db, task, not_ready_rows)
            stats["stale_logistics_notice_count"] = notice_count
            _finish_step(
                db,
                step,
                status="success",
                message=notice_message,
                stats={"notice_count": notice_count},
            )

        if ready_print_rows:
            step = _start_step(db, run.id, STEP_MOVE_TO_PRINTING, "转入待打印", {"order_ids": [row.id for row in ready_print_rows]})
            to_printing_rows = [row for row in ready_print_rows if row.biz_status != ORDER_STATUS_WAITING_PRINT]
            if to_printing_rows:
                _move_to_printing(db, to_printing_rows)
            stats["waiting_print_count"] = len(ready_print_rows)
            for row in ready_print_rows:
                _upsert_run_order(db, run.id, row, status_after=row.biz_status or "")
            _finish_step(
                db,
                step,
                status="success",
                message=f"已转入待打印 {len(to_printing_rows)} 条，本次可打印 {len(ready_print_rows)} 条",
                stats={"moved_to_waiting_print": len(to_printing_rows), "ready_to_print": len(ready_print_rows)},
            )

    waiting_print_rows = ready_print_rows
    if not waiting_print_rows:
        if not purchase_ready_order_ids:
            if stats["shipped_count"] > 0:
                summary = (
                    f"任务完成，选中订单 {stats['selected_orders']} 条，"
                    f"无需打印/采购订单已直接转为已发货 {stats['shipped_count']} 条"
                )
                return "success", summary, stats
            summary = (
                f"任务完成，选中订单 {stats['selected_orders']} 条，"
                f"暂无已同时获取货运单号和面单的待打印订单"
            )
            return "success", summary, stats

        order_ids = sorted(purchase_ready_order_ids)
        waiting_purchase_rows = db.scalars(select(Order).where(Order.id.in_(order_ids)).order_by(asc(Order.id))).all()
        purchase = _generate_purchase_and_move_to_picking(db, task, run, waiting_purchase_rows, stats)
        if not purchase:
            summary = f"任务完成，选中订单 {stats['selected_orders']} 条，待采购订单均因缺少中文名称被过滤"
            return "success", summary, stats
        summary = (
            f"任务完成，选中订单 {stats['selected_orders']} 条，"
            f"生成采购单 {purchase.purchase_no}，转配货 {stats['picking_count']} 条"
        )
        return "success", summary, stats

    step = _start_step(db, run.id, STEP_GENERATE_PDF, "生成平台PDF", {"order_ids": [row.id for row in waiting_print_rows]})
    pdf_map, cached, fetched, failed = await _ensure_labels_cached(db, waiting_print_rows, load_bytes=True)
    printer_map = _printer_setting_map(db)
    ordered_platforms = _ordered_platforms_for_print(waiting_print_rows, printer_map)
    missing_platform_settings = _missing_print_settings(ordered_platforms, printer_map)
    require_chinese_label_setting = _should_require_chinese_label_setting(db)
    missing_chinese_setting = require_chinese_label_setting and (
        PRINT_PLATFORM_CHINESE_LABEL not in printer_map or not (printer_map[PRINT_PLATFORM_CHINESE_LABEL].printer_name or "").strip()
    )
    if missing_platform_settings or missing_chinese_setting:
        missing_names = list(missing_platform_settings)
        if missing_chinese_setting:
            missing_names.append(PRINT_PLATFORM_CHINESE_LABEL)
        raise RuntimeError(f"缺少启用的打印设置或打印机：{', '.join(missing_names)}")

    oriented_pdf_map: dict[int, bytes] = {}
    platform_groups: dict[str, dict] = {platform: {"orders": [], "parts": []} for platform in ordered_platforms}
    for row in waiting_print_rows:
        platform = row.platform or ""
        platform_groups.setdefault(platform, {"orders": [], "parts": []})
        platform_groups[platform]["orders"].append(row)
        part = pdf_map.get(row.id)
        if part:
            print_setting = printer_map.get(platform)
            page_orientation = _print_setting_page_orientation(platform, print_setting)
            oriented_part = orient_pdf_bytes(part, page_orientation, target_size_mm=label_size_mm_for_platform(platform))
            oriented_pdf_map[row.id] = oriented_part
            platform_groups[platform]["parts"].append(oriented_part)

    pdf_backups: dict[str, str] = {}
    platform_print_order: list[str] = []
    ordered_print_rows: list[Order] = []
    for platform in ordered_platforms:
        group = platform_groups.get(platform) or {"orders": [], "parts": []}
        parts = group["parts"]
        if not parts:
            for row in group["orders"]:
                _upsert_run_order(db, run.id, row, pdf_generated=False, error_message="未获取到真实面单PDF，等待下次轮巡", needs_reprint=False)
            continue
        merged = _merge_pdf_parts(parts)
        backup_path = _backup_merged_pdf(platform or "unknown", run.id, merged)
        pdf_backups[platform] = backup_path
        platform_print_order.append(platform)
        stats["pdf_platforms"] = platform_print_order.copy()
        stats["pdf_platform_count"] += 1
        for row in group["orders"]:
            if pdf_map.get(row.id):
                ordered_print_rows.append(row)
                stats["pdf_success_count"] += 1
                _upsert_run_order(db, run.id, row, pdf_generated=True, pdf_file_path=backup_path)
            else:
                _upsert_run_order(db, run.id, row, pdf_generated=False, error_message="该订单缺少真实面单PDF，等待下次轮巡")

    chinese_label_backup_path = ""
    if ordered_print_rows and (PRINT_PLATFORM_CHINESE_LABEL in printer_map or require_chinese_label_setting):
        chinese_label_pdf = generate_chinese_label_pdf(_chinese_label_rows_for_orders(db, ordered_print_rows))
        chinese_label_backup_path = _backup_merged_pdf(PRINT_PLATFORM_CHINESE_LABEL, run.id, chinese_label_pdf)
        stats["chinese_label_pdf_generated"] = True
        chinese_setting = printer_map.get(PRINT_PLATFORM_CHINESE_LABEL)
        _upsert_run_document(
            db,
            run.id,
            PRINT_PLATFORM_CHINESE_LABEL,
            pdf_generated=True,
            pdf_file_path=chinese_label_backup_path,
            printer_name=(chinese_setting.printer_name or "").strip() if chinese_setting else "",
            print_submitted=False,
            print_message="中文标签PDF已生成，等待提交打印",
            needs_reprint=False,
        )
    _finish_step(
        db,
        step,
        status="success",
        message=f"平台PDF生成完成，缓存命中 {cached}，新拉取 {fetched}，失败 {failed}，中文标签 {'已生成' if chinese_label_backup_path else '未生成'}",
        stats={
            "cached": cached,
            "fetched": fetched,
            "failed": failed,
            "platforms": platform_print_order,
            "chinese_label_pdf_generated": bool(chinese_label_backup_path),
        },
    )

    monitor_printer_names = [
        (printer_map.get(platform).printer_name or "").strip()
        for platform in platform_print_order
        if printer_map.get(platform)
    ]
    if chinese_label_backup_path:
        chinese_setting = printer_map.get(PRINT_PLATFORM_CHINESE_LABEL)
        if chinese_setting and (chinese_setting.printer_name or "").strip():
            monitor_printer_names.append((chinese_setting.printer_name or "").strip())
    try:
        stats["printer_monitor"] = _run_printer_monitor_step(db, task, run, monitor_printer_names)
    except Exception as exc:
        stats["printer_monitor"] = [{"status": "error", "message": f"打印机状态监控调用异常: {exc}"}]

    step = _start_step(
        db,
        run.id,
        STEP_SUBMIT_PRINT,
        "提交打印任务",
        {"platforms": platform_print_order, "chinese_label": bool(chinese_label_backup_path)},
    )
    previous_printed_rows = _previous_printed_rows(db, run)
    print_ready_order_ids: set[int] = set()
    for platform in platform_print_order:
        group = platform_groups[platform]
        backup_path = pdf_backups.get(platform)
        print_setting = printer_map.get(platform)
        printer_name = (print_setting.printer_name or "").strip() if print_setting else ""
        printer_resolution, available_printers = _resolve_printer_for_setting(print_setting, printer_name)
        if printer_resolution.ambiguous:
            printer_name = printer_resolution.configured_name
        elif printer_resolution.resolved_name:
            _apply_resolved_printer_to_setting(db, print_setting, printer_resolution.resolved_name, available_printers)
            printer_name = printer_resolution.resolved_name
        page_orientation = _print_setting_page_orientation(platform, print_setting)
        target_size_mm = label_size_mm_for_platform(platform)
        submitted = False
        print_message = "未生成平台PDF"
        print_job_name = ""
        rows_with_pdf = [row for row in group["orders"] if pdf_map.get(row.id)]
        rows_to_print = [row for row in rows_with_pdf if row.id not in previous_printed_rows]
        print_backup_path = backup_path
        if rows_to_print and len(rows_to_print) != len(rows_with_pdf):
            print_backup_path = _backup_merged_pdf(platform or "unknown", run.id, _merge_pdf_parts([oriented_pdf_map[row.id] for row in rows_to_print]))
        if rows_to_print and print_backup_path:
            print_job_name = _build_print_job_name("auto", f"run{run.id}", platform or "unknown")
            if printer_resolution.ambiguous:
                submitted = False
                print_message = printer_resolution.message or _ambiguous_printer_message(printer_name)
            else:
                submitted, print_message = _submit_pdf_to_printer(
                    print_backup_path,
                    printer_name,
                    allow_offline_queue=True,
                    require_queue_observed=True,
                    job_name=print_job_name,
                    page_orientation=page_orientation,
                    target_size_mm=target_size_mm,
                )
            if submitted and _print_needs_manual_confirmation(print_message):
                stats["print_uncertain_count"] += len(rows_to_print)
                notified, notify_message = _notify_uncertain_prints(
                    db,
                    task,
                    run,
                    printer_name=printer_name,
                    platform=platform,
                    rows=rows_to_print,
                    pdf_path=print_backup_path,
                    print_message=print_message,
                )
                print_message = f"{print_message}；{notify_message}"
        elif rows_with_pdf and not rows_to_print:
            submitted = True
            print_message = "重试恢复：原运行已提交打印，本次跳过重复打印"
        for row in group["orders"]:
            has_pdf = bool(pdf_map.get(row.id))
            if not has_pdf:
                _upsert_run_order(
                    db,
                    run.id,
                    row,
                    printer_name=printer_name,
                    print_job_name="",
                    print_submitted=False,
                    print_message="该订单缺少真实面单PDF，未提交打印",
                    needs_reprint=False,
                )
                continue
            previous_print = previous_printed_rows.get(row.id)
            if previous_print:
                _upsert_run_order(
                    db,
                    run.id,
                    row,
                    printer_name=previous_print.printer_name or printer_name,
                    print_job_name=previous_print.print_job_name or "",
                    print_submitted=True,
                    print_message="重试恢复：原运行已提交打印，本次跳过重复打印",
                    needs_reprint=False,
                )
                print_ready_order_ids.add(row.id)
                continue
            row_print_submitted = bool(print_backup_path and submitted)
            _upsert_run_order(
                db,
                run.id,
                row,
                printer_name=printer_name,
                print_job_name=print_job_name,
                print_submitted=row_print_submitted,
                print_message=print_message,
                needs_reprint=bool(print_backup_path and not submitted),
            )
            if row_print_submitted:
                print_ready_order_ids.add(row.id)
        previous_success_count = sum(1 for row in group["orders"] if row.id in previous_printed_rows and pdf_map.get(row.id))
        current_success_count = len(rows_to_print) if print_backup_path and submitted else 0
        current_failed_count = len(rows_to_print) if print_backup_path and not submitted else 0
        stats["print_success_count"] += previous_success_count + current_success_count
        stats["print_failed_count"] += current_failed_count
    chinese_label_submitted = False
    chinese_label_message = "未生成中文标签PDF"
    chinese_label_job_name = ""
    if chinese_label_backup_path and stats["print_failed_count"] == 0:
        chinese_setting = printer_map.get(PRINT_PLATFORM_CHINESE_LABEL)
        chinese_printer_name = (chinese_setting.printer_name or "").strip() if chinese_setting else ""
        chinese_orientation = _print_setting_page_orientation(PRINT_PLATFORM_CHINESE_LABEL, chinese_setting)
        chinese_label_job_name = _build_print_job_name("auto", f"run{run.id}", PRINT_PLATFORM_CHINESE_LABEL)
        chinese_resolution, chinese_available_printers = _resolve_printer_for_setting(chinese_setting, chinese_printer_name)
        if chinese_resolution.ambiguous:
            chinese_label_submitted = False
            chinese_label_message = chinese_resolution.message or _ambiguous_printer_message(chinese_printer_name)
        else:
            if chinese_resolution.resolved_name:
                _apply_resolved_printer_to_setting(db, chinese_setting, chinese_resolution.resolved_name, chinese_available_printers)
                chinese_printer_name = chinese_resolution.resolved_name
            chinese_label_submitted, chinese_label_message = _submit_pdf_to_printer(
                chinese_label_backup_path,
                chinese_printer_name,
                allow_offline_queue=True,
                require_queue_observed=True,
                job_name=chinese_label_job_name,
                page_orientation=chinese_orientation,
                target_size_mm=None,
            )
        if chinese_label_submitted:
            stats["chinese_label_print_success_count"] = len(ordered_print_rows)
        else:
            stats["chinese_label_print_failed_count"] = len(ordered_print_rows)
            stats["print_failed_count"] += len(ordered_print_rows)
        if chinese_label_submitted and _print_needs_manual_confirmation(chinese_label_message):
            stats["print_uncertain_count"] += len(ordered_print_rows)
            notified, notify_message = _notify_uncertain_prints(
                db,
                task,
                run,
                printer_name=chinese_printer_name,
                platform=PRINT_PLATFORM_CHINESE_LABEL,
                rows=ordered_print_rows,
                pdf_path=chinese_label_backup_path,
                print_message=chinese_label_message,
            )
            chinese_label_message = f"{chinese_label_message}；{notify_message}"
        _upsert_run_document(
            db,
            run.id,
            PRINT_PLATFORM_CHINESE_LABEL,
            pdf_generated=True,
            pdf_file_path=chinese_label_backup_path,
            printer_name=chinese_printer_name,
            print_job_name=chinese_label_job_name,
            print_submitted=chinese_label_submitted,
            print_message=chinese_label_message,
            needs_reprint=not chinese_label_submitted,
        )
    elif chinese_label_backup_path:
        _upsert_run_document(
            db,
            run.id,
            PRINT_PLATFORM_CHINESE_LABEL,
            pdf_generated=True,
            pdf_file_path=chinese_label_backup_path,
            print_message="平台面单仍有打印失败，中文标签暂未提交打印",
            needs_reprint=True,
        )
    if print_ready_order_ids:
        _mark_labels_printed(db, list(print_ready_order_ids))
    _finish_step(
        db,
        step,
        status="success",
        message="打印提交步骤完成",
        stats={
            "print_success_count": stats["print_success_count"],
            "print_failed_count": stats["print_failed_count"],
            "print_uncertain_count": stats["print_uncertain_count"],
            "chinese_label_print_success_count": stats["chinese_label_print_success_count"],
            "chinese_label_print_failed_count": stats["chinese_label_print_failed_count"],
            "chinese_label_message": chinese_label_message,
            "chinese_label_job_name": chinese_label_job_name,
            "post_submit_printer_notification_count": len(stats["post_submit_printer_notifications"]),
            "post_submit_printer_notifications": stats["post_submit_printer_notifications"],
        },
    )
    if stats["print_failed_count"] > 0:
        raise RuntimeError(f"打印提交失败 {stats['print_failed_count']} 个PDF，已进入重试流程")

    printed_ready_order_ids = [row.id for row in waiting_print_rows if row.id in print_ready_order_ids]
    purchase_ready_order_ids.update(printed_ready_order_ids)
    if not purchase_ready_order_ids:
        summary = (
            f"任务完成，选中订单 {stats['selected_orders']} 条，"
            f"已就绪 {stats['logistics_ready_count']} 条，但暂无成功提交打印的订单"
        )
        return "success", summary, stats

    order_ids = sorted(purchase_ready_order_ids)
    waiting_purchase_rows = db.scalars(select(Order).where(Order.id.in_(order_ids)).order_by(asc(Order.id))).all()
    purchase = _generate_purchase_and_move_to_picking(db, task, run, waiting_purchase_rows, stats)
    if not purchase:
        summary = (
            f"任务完成，选中订单 {stats['selected_orders']} 条，"
            f"打印成功 {stats['print_success_count']} 条，采购单未生成：待采购订单均因缺少中文名称被过滤"
        )
        return "success", summary, stats

    summary = (
        f"任务完成，选中订单 {stats['selected_orders']} 条，"
        f"生成面单 {stats['pdf_success_count']} 条，打印成功 {stats['print_success_count']} 条，"
        f"生成采购单 {purchase.purchase_no}，转配货 {stats['picking_count']} 条"
    )
    return "success", summary, stats


def _mark_waiting_retry(
    db: Session,
    run: ScheduledTaskRun,
    task: ScheduledTask,
    *,
    reason: str,
    stats: dict | None = None,
) -> ScheduledTaskRun:
    now = _utc_now()
    next_retry_at = now + timedelta(minutes=_task_retry_interval_minutes(task))
    summary = f"{reason}；将在 {next_retry_at.replace(microsecond=0).isoformat()} 重试（{int(run.attempt_no or 0) + 1}/{int(run.max_retry_count or 0)}）"
    run.status = "waiting_retry"
    run.summary = summary
    run.stats_json = _initialize_post_print_monitor(db, run, stats, now=now)
    run.retry_reason = reason
    run.next_retry_at = next_retry_at
    run.ended_at = now
    task.last_run_at = run.ended_at
    task.last_status = "waiting_retry"
    task.last_message = summary
    db.commit()
    db.refresh(run)
    return run


def _mark_final_failed(
    db: Session,
    run: ScheduledTaskRun,
    task: ScheduledTask,
    *,
    reason: str,
    stats: dict | None = None,
) -> ScheduledTaskRun:
    _finish_run(db, run, task, status="failed", summary=reason, stats=stats)
    try:
        sent, message = send_final_failure_email(db, task, run)
        run.email_sent = bool(sent)
        run.email_error = "" if sent else message
    except Exception as mail_exc:
        run.email_sent = False
        run.email_error = str(mail_exc)
    db.commit()
    db.refresh(run)
    return run


def run_scheduled_task(
    task_id: int,
    trigger_mode: str = "scheduler",
    *,
    attempt_no: int = 0,
    parent_run_id: int | None = None,
    original_run_id: int | None = None,
) -> dict:
    db = SessionLocal()
    task = db.get(ScheduledTask, task_id)
    if not task:
        db.close()
        raise ValueError(f"定时任务不存在: {task_id}")
    if not task.enabled and trigger_mode in {"scheduler", "catchup"}:
        db.close()
        return {"id": task_id, "status": "skipped", "message": "任务已停用"}

    run = _create_run(
        db,
        task,
        trigger_mode,
        attempt_no=attempt_no,
        parent_run_id=parent_run_id,
        original_run_id=original_run_id,
    )
    try:
        status, summary, stats = asyncio.run(asyncio.wait_for(_auto_order_pipeline_async(db, task, run), timeout=_task_timeout_seconds(task)))
        _finish_run(db, run, task, status=status, summary=summary, stats=stats)
        _enqueue_purchase_order_notice_from_stats(stats, source="scheduled_task")
        _enqueue_order_follow_up_export_after_success(run, status)
        return {"run": _run_dto(run), "task_id": task.id, "status": status, "message": summary}
    except TimeoutError as exc:
        reason = f"任务运行超时，已超过 {_task_timeout_seconds(task) // 60} 分钟"
        if int(run.attempt_no or 0) < int(run.max_retry_count or 0):
            _mark_waiting_retry(db, run, task, reason=reason, stats=run.stats_json or {})
            return {"run": _run_dto(run), "task_id": task.id, "status": run.status, "message": run.summary}
        _mark_final_failed(db, run, task, reason=reason, stats=run.stats_json or {})
        raise RuntimeError(reason) from exc
    except Exception as exc:
        reason = str(exc)
        if int(run.attempt_no or 0) < int(run.max_retry_count or 0):
            _mark_waiting_retry(db, run, task, reason=reason, stats=run.stats_json or {})
            return {"run": _run_dto(run), "task_id": task.id, "status": run.status, "message": run.summary}
        _mark_final_failed(db, run, task, reason=reason, stats=run.stats_json or {})
        raise
    finally:
        db.close()


def _enqueue_purchase_order_notice_from_stats(stats: dict | None, *, source: str) -> None:
    if not stats:
        return
    try:
        purchase_order_id = int(stats.get("purchase_order_id") or 0)
    except (TypeError, ValueError):
        return
    if purchase_order_id:
        enqueue_purchase_order_wecom_notification(purchase_order_id, source=source)


def _enqueue_order_follow_up_export_after_success(run: ScheduledTaskRun, status: str) -> None:
    if status != "success" or not run.id:
        return
    try:
        enqueue_order_follow_up_export(int(run.id))
    except Exception:
        logger.exception("Failed to enqueue order follow up export run_id=%s", run.id)


def process_due_task_retries() -> int:
    db = SessionLocal()
    try:
        due_runs = db.scalars(
            select(ScheduledTaskRun)
            .where(
                ScheduledTaskRun.status == "waiting_retry",
                ScheduledTaskRun.next_retry_at.is_not(None),
                ScheduledTaskRun.next_retry_at <= _utc_now(),
            )
            .order_by(asc(ScheduledTaskRun.next_retry_at), asc(ScheduledTaskRun.id))
            .limit(10)
        ).all()
        retry_specs: list[tuple[int, int, int, int]] = []
        for run in due_runs:
            task = db.get(ScheduledTask, run.scheduled_task_id) if run.scheduled_task_id else None
            if not task or not task.enabled:
                continue
            run.status = "retrying"
            run.next_retry_at = None
            db.flush()
            retry_specs.append((task.id, int(run.attempt_no or 0) + 1, run.id, run.original_run_id or run.id))
        db.commit()
    finally:
        db.close()

    executed = 0
    for task_id, attempt_no, parent_run_id, original_run_id in retry_specs:
        try:
            run_scheduled_task(
                task_id,
                "retry",
                attempt_no=attempt_no,
                parent_run_id=parent_run_id,
                original_run_id=original_run_id,
            )
        except Exception:
            pass
        executed += 1
    return executed


def list_task_runs(task_id: int | None = None, limit_count: int = 200) -> list[dict]:
    db = SessionLocal()
    try:
        stmt = select(ScheduledTaskRun).order_by(ScheduledTaskRun.id.desc()).limit(limit_count)
        if task_id:
            stmt = select(ScheduledTaskRun).where(ScheduledTaskRun.scheduled_task_id == task_id).order_by(ScheduledTaskRun.id.desc()).limit(limit_count)
        rows = db.scalars(stmt).all()
        return [_run_dto(row) for row in rows]
    finally:
        db.close()


def list_task_run_steps(run_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.scalars(select(ScheduledTaskRunStep).where(ScheduledTaskRunStep.run_id == run_id).order_by(ScheduledTaskRunStep.id.asc())).all()
        return [_step_dto(row) for row in rows]
    finally:
        db.close()


def refresh_reprint_candidates(db: Session, run_id: int) -> None:
    rows = db.scalars(
        select(ScheduledTaskRunOrder)
        .where(
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.pdf_generated.is_(True),
            ScheduledTaskRunOrder.pdf_file_path != "",
        )
        .order_by(ScheduledTaskRunOrder.id.asc())
    ).all()
    changed = False
    for row in rows:
        if not row.printer_name:
            if not row.needs_reprint:
                row.needs_reprint = True
                row.print_message = "缺少打印机名称，无法确认打印状态"
                changed = True
            continue
        document_name = row.print_job_name or Path(row.pdf_file_path or "").name
        printer_resolution = _resolve_printer_identity(row.printer_name, _server_printer_identities())
        snapshot = _print_queue_snapshot(printer_resolution.resolved_name or row.printer_name, document_name)
        if not snapshot.get("exists"):
            if not row.needs_reprint:
                row.needs_reprint = True
                row.print_message = f"打印机不存在: {row.printer_name}"
                changed = True
            continue
        job_count = int(snapshot.get("job_count") or 0)
        job_status = str(snapshot.get("job_status") or "")
        if snapshot.get("offline") and job_count > 0:
            row.needs_reprint = False
            row.print_message = f"打印机脱机，任务已在队列中: {row.printer_name}"
            changed = True
        elif snapshot.get("offline"):
            row.needs_reprint = True
            row.print_message = f"打印机脱机，未确认打印完成: {row.printer_name}"
            changed = True
        elif job_count > 0 and any(token in job_status.lower() for token in ("error", "paused", "offline")):
            row.needs_reprint = True
            row.print_message = f"打印队列异常: {job_status or row.printer_name}"
            changed = True
    if changed:
        db.commit()


def list_task_run_orders(run_id: int, needs_reprint: bool | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        if needs_reprint is True:
            refresh_reprint_candidates(db, run_id)
        stmt = select(ScheduledTaskRunOrder).where(ScheduledTaskRunOrder.run_id == run_id).order_by(ScheduledTaskRunOrder.id.asc())
        if needs_reprint is not None:
            stmt = stmt.where(ScheduledTaskRunOrder.needs_reprint == needs_reprint)
        rows = db.scalars(stmt).all()
        return [_run_order_dto(row) for row in rows]
    finally:
        db.close()


def _manual_reprint_resume_candidates(db: Session, run_id: int) -> list[Order]:
    return db.scalars(
        select(Order)
        .join(ScheduledTaskRunOrder, ScheduledTaskRunOrder.order_id == Order.id)
        .where(
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.print_submitted.is_(True),
            ScheduledTaskRunOrder.needs_reprint.is_(False),
            ScheduledTaskRunOrder.purchase_order_id.is_(None),
            Order.label_printed_at.is_not(None),
            Order.biz_status.in_((ORDER_STATUS_WAITING_PRINT, ORDER_STATUS_WAITING_PURCHASE)),
            ~_has_purchase_order_for_order(Order.id),
        )
        .order_by(asc(Order.id))
    ).all()


def _remaining_reprint_count(db: Session, run_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(ScheduledTaskRunOrder.id)).where(
                ScheduledTaskRunOrder.run_id == run_id,
                ScheduledTaskRunOrder.needs_reprint.is_(True),
            )
        )
        or 0
    )


def _resume_run_after_manual_reprint(db: Session, run: ScheduledTaskRun | None) -> PurchaseOrder | None:
    if not run or (run.status or "") in {"success", "partial_success"}:
        return None
    task = db.get(ScheduledTask, run.scheduled_task_id) if run.scheduled_task_id else None
    if not task:
        return None

    stats = dict(run.stats_json or {})
    candidate_rows = _manual_reprint_resume_candidates(db, run.id)
    rules = load_enabled_logistics_rules(db)
    candidate_rows, unmatched_rule_rows = split_logistics_rule_eligible_orders(
        candidate_rows,
        rules,
        matched_at=_utc_now(),
    )
    if unmatched_rule_rows:
        _move_logistics_rule_unmatched_to_shipped(db, run, unmatched_rule_rows, stats)
    stats["manual_reprint_resume_order_count"] = len(candidate_rows)
    stats["manual_reprint_resume_unmatched_shipped_count"] = len(unmatched_rule_rows)
    purchase = _generate_purchase_and_move_to_picking(db, task, run, candidate_rows, stats) if candidate_rows else None
    remaining_reprint_count = _remaining_reprint_count(db, run.id)
    stats["remaining_reprint_count"] = remaining_reprint_count
    run.stats_json = _json_object(stats)

    if remaining_reprint_count > 0:
        run.summary = (
            f"手动重打已恢复 {len(candidate_rows)} 条，"
            f"仍有 {remaining_reprint_count} 条需要重打"
        )
        task.last_run_at = _utc_now()
        task.last_status = run.status or "failed"
        task.last_message = run.summary
        db.commit()
        db.refresh(run)
        db.refresh(task)
        return purchase

    if purchase:
        summary = f"手动重打成功，已继续生成采购单 {purchase.purchase_no}，转配货 {stats.get('picking_count', 0)} 条"
    elif candidate_rows:
        summary = "手动重打成功，待采购订单均因缺少中文名称被过滤"
    else:
        summary = "手动重打成功，所有失败打印已恢复"
    run.status = "success"
    run.summary = summary
    run.next_retry_at = None
    run.retry_reason = ""
    run.ended_at = _utc_now()
    task.last_run_at = run.ended_at
    task.last_status = run.status
    task.last_message = run.summary
    db.commit()
    db.refresh(run)
    db.refresh(task)
    return purchase


def _run_order_reprint_rows_for_source(db: Session, row: ScheduledTaskRunOrder) -> list[ScheduledTaskRunOrder]:
    if int(row.order_id or 0) == 0:
        return [row]
    return db.scalars(
        select(ScheduledTaskRunOrder).where(
            ScheduledTaskRunOrder.run_id == row.run_id,
            ScheduledTaskRunOrder.pdf_file_path == row.pdf_file_path,
            ScheduledTaskRunOrder.order_id != 0,
        )
    ).all()


def _retry_run_order_rows_print(
    db: Session,
    *,
    source_row: ScheduledTaskRunOrder,
    sibling_rows: list[ScheduledTaskRunOrder],
    print_setting: PlatformPrintSetting | None = None,
) -> dict:
    pdf_path = (source_row.pdf_file_path or "").strip()
    if not pdf_path:
        raise ValueError("缺少PDF备份路径")
    if not Path(pdf_path).exists():
        raise ValueError("PDF备份文件不存在")
    if print_setting is None:
        print_setting = db.scalar(
            select(PlatformPrintSetting).where(
                PlatformPrintSetting.enabled == True,
                PlatformPrintSetting.platform == (source_row.platform or ""),
                PlatformPrintSetting.document_type == PRINT_DOCUMENT_TYPE_LABEL,
            )
        )
    page_orientation = _print_setting_page_orientation(source_row.platform, print_setting)
    print_job_name = _build_print_job_name(source_row.platform or "unknown")
    configured_printer_name = (print_setting.printer_name or "").strip() if print_setting else source_row.printer_name or ""
    printer_resolution, available_printers = _resolve_printer_for_setting(print_setting, configured_printer_name)
    printer_name = configured_printer_name
    if printer_resolution.ambiguous:
        submitted = False
        message = printer_resolution.message or _ambiguous_printer_message(configured_printer_name)
    else:
        if printer_resolution.resolved_name:
            _apply_resolved_printer_to_setting(db, print_setting, printer_resolution.resolved_name, available_printers)
            printer_name = printer_resolution.resolved_name
        submitted, message = _submit_pdf_to_printer(
            pdf_path,
            printer_name,
            allow_offline_queue=True,
            require_queue_observed=True,
            job_name=print_job_name,
            page_orientation=page_orientation,
            target_size_mm=None if source_row.platform == PRINT_PLATFORM_CHINESE_LABEL else label_size_mm_for_platform(source_row.platform),
        )
    for sibling in sibling_rows:
        sibling.print_job_name = print_job_name
        sibling.print_submitted = submitted
        sibling.print_message = message
        sibling.needs_reprint = not submitted
        if printer_name:
            sibling.printer_name = printer_name
    order_ids = [sibling.order_id for sibling in sibling_rows if int(sibling.order_id or 0) != 0]
    if submitted and order_ids:
        _mark_labels_printed(db, order_ids)
    if submitted:
        _resume_run_after_manual_reprint(db, db.get(ScheduledTaskRun, source_row.run_id))
    return _run_order_dto(source_row)


def retry_run_order_print(run_order_id: int) -> dict:
    db = SessionLocal()
    try:
        row = db.get(ScheduledTaskRunOrder, run_order_id)
        if not row:
            raise ValueError("运行订单记录不存在")
        print_setting = db.scalar(
            select(PlatformPrintSetting).where(
                PlatformPrintSetting.enabled == True,
                PlatformPrintSetting.platform == (row.platform or ""),
                PlatformPrintSetting.document_type == PRINT_DOCUMENT_TYPE_LABEL,
            )
        )
        result = _retry_run_order_rows_print(
            db,
            source_row=row,
            sibling_rows=_run_order_reprint_rows_for_source(db, row),
            print_setting=print_setting,
        )
        db.commit()
        db.refresh(row)
        return result
    finally:
        db.close()


def retry_run_platform_print(run_id: int, platform: str, *, failed_only: bool = True) -> dict:
    db = SessionLocal()
    try:
        platform_key = (platform or "").strip()
        if not platform_key:
            raise ValueError("平台不能为空")
        run = db.get(ScheduledTaskRun, run_id)
        if not run:
            raise ValueError("任务运行记录不存在")
        refresh_reprint_candidates(db, run_id)
        filters = [
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.platform == platform_key,
            ScheduledTaskRunOrder.pdf_generated.is_(True),
            ScheduledTaskRunOrder.pdf_file_path != "",
        ]
        if failed_only:
            filters.append(ScheduledTaskRunOrder.needs_reprint.is_(True))
        rows = db.scalars(
            select(ScheduledTaskRunOrder)
            .where(*filters)
            .order_by(ScheduledTaskRunOrder.id.asc())
        ).all()
        if not rows:
            raise ValueError("该平台没有可重打的打印记录")
        print_setting = db.scalar(
            select(PlatformPrintSetting).where(
                PlatformPrintSetting.enabled == True,
                PlatformPrintSetting.platform == platform_key,
                PlatformPrintSetting.document_type == PRINT_DOCUMENT_TYPE_LABEL,
            )
        )
        printed_paths: set[str] = set()
        result = {}
        for row in rows:
            pdf_path = (row.pdf_file_path or "").strip()
            if not pdf_path or pdf_path in printed_paths:
                continue
            printed_paths.add(pdf_path)
            result = _retry_run_order_rows_print(
                db,
                source_row=row,
                sibling_rows=_run_order_reprint_rows_for_source(db, row),
                print_setting=print_setting,
            )
        if not result:
            raise ValueError("该平台没有可重打的PDF备份")
        db.commit()
        return {
            "run_id": run_id,
            "platform": platform_key,
            "pdf_count": len(printed_paths),
            **result,
        }
    finally:
        db.close()
