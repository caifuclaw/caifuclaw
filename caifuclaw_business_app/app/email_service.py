from __future__ import annotations

import smtplib
import base64
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from .credential_manager import get_credential_manager
from .models import EmailSmtpSetting, ScheduledTask, ScheduledTaskRun, ScheduledTaskRunOrder


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "pdf"


EMAIL_PROVIDER_PRESETS: dict[str, dict] = {
    "qq": {
        "code": "qq",
        "name": "QQ邮箱",
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "use_ssl": True,
        "auth_code_hint": "请输入 QQ 邮箱 SMTP 授权码，不是登录密码",
        "sender_hint": "demo@example.invalid",
    },
    "163": {
        "code": "163",
        "name": "163邮箱",
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
        "use_ssl": True,
        "auth_code_hint": "请输入 163 邮箱客户端授权密码，不是登录密码",
        "sender_hint": "demo@example.invalid",
    },
    "custom": {
        "code": "custom",
        "name": "自定义 SMTP",
        "smtp_host": "",
        "smtp_port": 465,
        "use_ssl": True,
        "auth_code_hint": "请输入邮箱服务商提供的 SMTP 授权码或密码",
        "sender_hint": "demo@example.invalid",
    },
}

EMAIL_NOTIFICATION_WANBANG_TRACKING_FAILURE = "wanbang_tracking_failure"
EMAIL_NOTIFICATION_BSI_ADDRESS_ANOMALY = "bsi_address_anomaly"


def list_email_provider_presets() -> list[dict]:
    return [dict(item) for item in EMAIL_PROVIDER_PRESETS.values()]


def apply_provider_preset(provider: str, smtp_host: str = "", smtp_port: int | None = None, use_ssl: bool | None = None) -> tuple[str, int, bool]:
    code = (provider or "qq").strip().lower()
    preset = EMAIL_PROVIDER_PRESETS.get(code, EMAIL_PROVIDER_PRESETS["qq"])
    if code == "custom":
        return (smtp_host or "").strip(), int(smtp_port or 465), True if use_ssl is None else bool(use_ssl)
    return preset["smtp_host"], int(preset["smtp_port"]), bool(preset["use_ssl"])


def get_email_setting(db: Session) -> EmailSmtpSetting:
    row = db.get(EmailSmtpSetting, 1)
    if row is None:
        row = EmailSmtpSetting(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def encrypt_auth_code(auth_code: str) -> bytes | None:
    value = (auth_code or "").strip()
    if not value:
        return None
    return get_credential_manager().encrypt_credentials({"auth_code": value})


def decrypt_auth_code(row: EmailSmtpSetting) -> str:
    data = get_credential_manager().decrypt_credentials(row.encrypted_auth_code)
    return str(data.get("auth_code") or "")


def parse_recipients(value: str) -> list[str]:
    recipients: list[str] = []
    for part in (value or "").replace("\n", ",").replace(";", ",").split(","):
        email = part.strip()
        if email:
            recipients.append(email)
    return recipients


def notification_recipient_values(setting: EmailSmtpSetting) -> dict[str, str]:
    stored = setting.notification_recipients if isinstance(getattr(setting, "notification_recipients", None), dict) else {}
    return {
        EMAIL_NOTIFICATION_WANBANG_TRACKING_FAILURE: str(stored.get(EMAIL_NOTIFICATION_WANBANG_TRACKING_FAILURE) or "").strip(),
        EMAIL_NOTIFICATION_BSI_ADDRESS_ANOMALY: str(stored.get(EMAIL_NOTIFICATION_BSI_ADDRESS_ANOMALY) or "").strip(),
    }


def notification_recipients_for(setting: EmailSmtpSetting, notification_type: str) -> list[str]:
    return parse_recipients(notification_recipient_values(setting).get(notification_type, ""))


def _smtp_auth_login(smtp: smtplib.SMTP, sender_email: str, auth_code: str) -> None:
    code, _message = smtp.docmd("AUTH", "LOGIN")
    if code != 334:
        raise smtplib.SMTPAuthenticationError(code, _message)
    code, _message = smtp.docmd(base64.b64encode(sender_email.encode("utf-8")).decode("ascii"))
    if code != 334:
        raise smtplib.SMTPAuthenticationError(code, _message)
    code, _message = smtp.docmd(base64.b64encode(auth_code.encode("utf-8")).decode("ascii"))
    if code != 235:
        raise smtplib.SMTPAuthenticationError(code, _message)


def send_email(
    setting: EmailSmtpSetting,
    recipients: list[str],
    subject: str,
    body: str,
    attachments: list[EmailAttachment] | None = None,
) -> None:
    if not setting.enabled:
        raise RuntimeError("邮件通知未启用")
    if not recipients:
        raise RuntimeError("未配置收件人")
    sender_email = (setting.sender_email or "").strip()
    if not sender_email:
        raise RuntimeError("未配置发件邮箱")
    auth_code = decrypt_auth_code(setting)
    if not auth_code:
        raise RuntimeError("未配置 SMTP 授权码")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(((setting.sender_name or "").strip() or sender_email, sender_email))
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    for attachment in attachments or []:
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )

    host = (setting.smtp_host or "smtp.qq.com").strip()
    port = int(setting.smtp_port or 465)
    try:
        if setting.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
                smtp.ehlo()
                _smtp_auth_login(smtp, sender_email, auth_code)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                _smtp_auth_login(smtp, sender_email, auth_code)
                smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        detail = ""
        if exc.smtp_error:
            detail = exc.smtp_error.decode("utf-8", errors="ignore") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        if "service is not open" in detail.lower() or "password is incorrect" in detail.lower() or "account is abnormal" in detail.lower():
            raise RuntimeError("SMTP 认证失败：账号异常、SMTP 服务未开启、授权码不正确、登录频率受限或邮箱服务忙") from exc
        raise RuntimeError(f"SMTP 认证失败：{detail or '请确认发件邮箱和授权码正确，并已开启邮箱 SMTP 服务'}") from exc
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPHeloError) as exc:
        raise RuntimeError(
            f"SMTP 服务器连接中断，请确认 {host}:{port}、SSL 设置、邮箱 SMTP 服务开关和授权码是否正确"
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise RuntimeError(f"连接 SMTP 服务器超时，请确认网络可访问 {host}:{port}") from exc
    except OSError as exc:
        raise RuntimeError(f"连接 SMTP 服务器失败：{exc}") from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"SMTP 发送失败：{exc}") from exc


def _safe_attachment_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in (value or "").strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:180] or "failed_print.pdf"


def _failed_print_pdf_attachments(db: Session, run: ScheduledTaskRun) -> tuple[list[EmailAttachment], list[str]]:
    rows = db.scalars(
        select(ScheduledTaskRunOrder)
        .where(
            ScheduledTaskRunOrder.run_id == run.id,
            ScheduledTaskRunOrder.needs_reprint == True,
            ScheduledTaskRunOrder.pdf_generated == True,
            ScheduledTaskRunOrder.pdf_file_path != "",
        )
        .order_by(asc(ScheduledTaskRunOrder.platform), asc(ScheduledTaskRunOrder.id))
    ).all()

    attachments: list[EmailAttachment] = []
    warnings: list[str] = []
    seen_paths: set[Path] = set()
    used_filenames: set[str] = set()
    for row in rows:
        raw_path = (row.pdf_file_path or "").strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            resolved = path.resolve()
        except (OSError, ValueError) as exc:
            warnings.append(f"{raw_path}: 路径无效，{exc}")
            continue
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        if resolved.suffix.lower() != ".pdf" or not resolved.is_file():
            warnings.append(f"{raw_path}: PDF 文件不存在")
            continue
        try:
            content = resolved.read_bytes()
        except OSError as exc:
            warnings.append(f"{raw_path}: 读取失败，{exc}")
            continue
        if not content.startswith(b"%PDF"):
            warnings.append(f"{raw_path}: 文件不是有效 PDF")
            continue

        platform = _safe_attachment_filename(row.platform or "unknown").removesuffix(".pdf")
        filename = _safe_attachment_filename(f"{platform}_{resolved.name}")
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        if filename in used_filenames:
            filename = _safe_attachment_filename(f"{platform}_{len(used_filenames) + 1}_{resolved.name}")
            if not filename.lower().endswith(".pdf"):
                filename = f"{filename}.pdf"
        used_filenames.add(filename)
        attachments.append(EmailAttachment(filename=filename, content=content))

    return attachments, warnings


def build_final_failure_email(
    task: ScheduledTask,
    run: ScheduledTaskRun,
    attachment_filenames: list[str] | None = None,
    attachment_warnings: list[str] | None = None,
) -> tuple[str, str]:
    attachment_filenames = attachment_filenames or []
    attachment_warnings = attachment_warnings or []
    extra_lines: list[str] = []
    if attachment_filenames:
        extra_lines.extend(
            [
                "",
                "已随邮件附上打印失败的 PDF 文件：",
                *[f"- {filename}" for filename in attachment_filenames],
            ]
        )
    if attachment_warnings:
        extra_lines.extend(
            [
                "",
                "以下打印失败 PDF 未能作为附件发送：",
                *[f"- {warning}" for warning in attachment_warnings[:10]],
            ]
        )
        if len(attachment_warnings) > 10:
            extra_lines.append(f"- 其余 {len(attachment_warnings) - 10} 个文件请登录后台查看")
    subject = f"[CaifuClaw AI] 定时任务最终失败：{task.name}"
    body = "\n".join(
        [
            "定时任务最终失败，已达到最大重试次数。",
            "",
            f"任务名称：{task.name}",
            f"任务类型：{task.task_type}",
            f"运行ID：{run.id}",
            f"尝试次数：{run.attempt_no}/{run.max_retry_count}",
            f"触发方式：{run.trigger_mode}",
            f"开始时间：{run.started_at}",
            f"结束时间：{run.ended_at or ''}",
            f"失败原因：{run.summary or run.retry_reason or '未知错误'}",
            *extra_lines,
            "",
            "请登录 CaifuClaw AI 后台查看任务运行详情。",
        ]
    )
    return subject, body


def send_final_failure_email(db: Session, task: ScheduledTask, run: ScheduledTaskRun) -> tuple[bool, str]:
    settings = task.settings if isinstance(task.settings, dict) else {}
    if not settings.get("failure_email_enabled"):
        return False, "任务未启用失败邮件通知"
    recipients = parse_recipients(str(settings.get("failure_email_recipients") or ""))
    if not recipients:
        return False, "未配置收件人"

    attachments, attachment_warnings = _failed_print_pdf_attachments(db, run)
    subject, body = build_final_failure_email(
        task,
        run,
        [attachment.filename for attachment in attachments],
        attachment_warnings,
    )
    send_email(get_email_setting(db), recipients, subject, body, attachments=attachments)
    if attachments:
        return True, f"邮件已发送，附件 {len(attachments)} 个"
    if attachment_warnings:
        return True, f"邮件已发送，{len(attachment_warnings)} 个PDF未能附加"
    return True, "邮件已发送"
