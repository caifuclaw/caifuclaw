from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from common.wecom_robot import WeComRobotClient, WeComRobotError, WeComRobotSettings

from .credential_manager import get_credential_manager
from .database import SessionLocal
from .models import LocalUser, WeComRobotSetting


DEFAULT_WECOM_PROMPT = "你有新的任务，请处理"
WECOM_TEST_MENTION_CONTENT = "@"
WECOM_TEST_MENTION_SENT = "默认提示语为空，已按默认提醒用户发送 @ 测试"
WECOM_TEST_MESSAGE_SKIPPED = "默认提示语为空，未发送企业微信测试消息"


def get_wecom_robot_setting(db: Session) -> WeComRobotSetting:
    row = db.get(WeComRobotSetting, 1)
    if row is None:
        row = WeComRobotSetting(
            id=1,
            timeout_seconds=30,
            max_retries=2,
            rate_limit_per_minute=20,
            default_mentioned_user_ids="[]",
            default_mentioned_list="[]",
            default_mentioned_mobile_list="[]",
            default_prompt=DEFAULT_WECOM_PROMPT,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def encrypt_wecom_webhook_url(webhook_url: str) -> bytes | None:
    value = (webhook_url or "").strip()
    if not value:
        return None
    return get_credential_manager().encrypt_credentials({"webhook_url": value})


def decrypt_wecom_webhook_url(row: WeComRobotSetting) -> str:
    data = get_credential_manager().decrypt_credentials(row.encrypted_webhook_url)
    return str(data.get("webhook_url") or "")


def mask_wecom_webhook_url(webhook_url: str) -> str:
    value = (webhook_url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    key = (parse_qs(parsed.query).get("key") or [""])[0].strip()
    if key:
        key = "********" if len(key) <= 8 else f"{key[:4]}****{key[-4:]}"
    else:
        key = "********"
    return f"{parsed.scheme or 'https'}://{parsed.netloc}{parsed.path}?key={key}"


def load_wecom_robot_settings_from_db(db: Session | None = None) -> WeComRobotSettings:
    owned_session = False
    if db is None:
        db = SessionLocal()
        owned_session = True
    try:
        row = get_wecom_robot_setting(db)
        webhook_url = decrypt_wecom_webhook_url(row).strip() if row.encrypted_webhook_url else ""
        if not webhook_url:
            raise WeComRobotError("WeCom robot webhook URL is not configured in system settings.")
        mentioned_mobile_list = _mentioned_mobile_list_from_users(db, _loads_int_list(row.default_mentioned_user_ids))
        legacy_mobile_list = _loads_string_list(row.default_mentioned_mobile_list)
        return WeComRobotSettings(
            webhook_url=webhook_url,
            timeout_seconds=float(row.timeout_seconds or 30),
            max_retries=max(0, int(row.max_retries or 0)),
            retry_backoff_seconds=1,
            rate_limit_per_minute=max(1, int(row.rate_limit_per_minute or 20)),
            default_mentioned_list=tuple(_loads_string_list(row.default_mentioned_list)),
            default_mentioned_mobile_list=tuple(mentioned_mobile_list or legacy_mobile_list),
            default_prompt=(row.default_prompt or "").strip(),
        )
    finally:
        if owned_session:
            db.close()


def dumps_string_list(values: list[str] | tuple[str, ...] | None) -> str:
    return json.dumps(normalize_string_list(values), ensure_ascii=False)


def dumps_int_list(values: list[int] | tuple[int, ...] | None) -> str:
    return json.dumps(normalize_int_list(values), ensure_ascii=False)


def loads_string_list(value: str | None) -> list[str]:
    return _loads_string_list(value)


def loads_int_list(value: str | None) -> list[int]:
    return _loads_int_list(value)


def normalize_string_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values or []:
        cleaned = str(item or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def normalize_int_list(values: list[int] | tuple[int, ...] | None) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for item in values or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def mentioned_mobile_list_from_user_ids(db: Session, user_ids: list[int] | tuple[int, ...] | None) -> list[str]:
    return _mentioned_mobile_list_from_users(db, normalize_int_list(user_ids))


def send_wecom_robot_test_message(db: Session, content: str | None = None) -> dict:
    message = (content or "").strip()
    if not message:
        row = get_wecom_robot_setting(db)
        mentioned_list = _loads_string_list(row.default_mentioned_list)
        mentioned_mobile_list = _mentioned_mobile_list_from_users(
            db,
            _loads_int_list(row.default_mentioned_user_ids),
        ) or _loads_string_list(row.default_mentioned_mobile_list)
        if not mentioned_list and not mentioned_mobile_list:
            return {"status": "skipped", "message": WECOM_TEST_MESSAGE_SKIPPED}
        settings = load_wecom_robot_settings_from_db(db)
        with WeComRobotClient(settings) as client:
            client.send_text(
                WECOM_TEST_MENTION_CONTENT,
                mentioned_list=mentioned_list,
                mentioned_mobile_list=mentioned_mobile_list,
            )
        return {"status": "mentioned", "message": WECOM_TEST_MENTION_SENT}
    settings = load_wecom_robot_settings_from_db(db)
    with WeComRobotClient(settings) as client:
        return client.send_text(message)


def validate_wecom_webhook_url(webhook_url: str) -> str:
    value = (webhook_url or "").strip()
    parsed = urlparse(value)
    key = (parse_qs(parsed.query).get("key") or [""])[0].strip()
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.path.endswith("/cgi-bin/webhook/send") or not key:
        raise WeComRobotError("webhook_url 必须是有效的企业微信群机器人 webhook 地址")
    return value


def _loads_string_list(value: str | None) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return normalize_string_list([str(item) for item in data])


def _loads_int_list(value: str | None) -> list[int]:
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return normalize_int_list(data)


def _mentioned_mobile_list_from_users(db: Session, user_ids: list[int]) -> list[str]:
    if not user_ids:
        return []
    rows = db.query(LocalUser).filter(LocalUser.id.in_(user_ids), LocalUser.enabled.is_(True)).all()
    mobile_by_id = {int(row.id): (row.wecom_mobile or "").strip() for row in rows}
    result: list[str] = []
    seen: set[str] = set()
    for user_id in user_ids:
        mobile = mobile_by_id.get(int(user_id), "")
        if not mobile or mobile in seen:
            continue
        seen.add(mobile)
        result.append(mobile)
    return result
