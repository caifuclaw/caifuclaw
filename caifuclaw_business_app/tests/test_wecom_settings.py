from pathlib import Path
import sys
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.credential_manager import CredentialManager
from app.database import Base
from app.models import LocalUser, WeComRobotSetting
from app.main import _validate_wecom_robot_payload, _wecom_mention_user_option_dto
from app.schemas import WeComRobotSettingUpdateRequest
from app.wecom_service import (
    DEFAULT_WECOM_PROMPT,
    dumps_int_list,
    dumps_string_list,
    encrypt_wecom_webhook_url,
    get_wecom_robot_setting,
    load_wecom_robot_settings_from_db,
    send_wecom_robot_test_message,
    validate_wecom_webhook_url,
    WECOM_TEST_MENTION_CONTENT,
    WECOM_TEST_MENTION_SENT,
    WECOM_TEST_MESSAGE_SKIPPED,
)
from app.purchase_order_notification import (
    PurchaseOrderNoticeRow,
    TABLE_COLUMN_WIDTHS,
    TABLE_HEADER_HEIGHT,
    TABLE_ROW_MIN_HEIGHT,
    TITLE_HEIGHT,
    group_purchase_order_notice_rows,
    render_purchase_order_notice_image,
    send_purchase_order_wecom_notification,
)
from app import purchase_order_notification as purchase_order_notification_module


def test_get_wecom_robot_setting_initializes_defaults(monkeypatch):
    monkeypatch.setattr(
        "app.wecom_service.get_credential_manager",
        lambda: CredentialManager(CredentialManager.generate_key()),
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[LocalUser.__table__, WeComRobotSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        row = get_wecom_robot_setting(db)

    assert row.id == 1
    assert row.timeout_seconds == 30
    assert row.max_retries == 2
    assert row.rate_limit_per_minute == 20
    assert row.default_mentioned_list == "[]"
    assert row.default_mentioned_mobile_list == "[]"
    assert row.default_prompt == DEFAULT_WECOM_PROMPT
    assert row.purchase_order_notify_enabled is False


def test_load_wecom_robot_settings_from_db_returns_decrypted_values(monkeypatch):
    manager = CredentialManager(CredentialManager.generate_key())
    monkeypatch.setattr("app.wecom_service.get_credential_manager", lambda: manager)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[LocalUser.__table__, WeComRobotSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        db.add(
            WeComRobotSetting(
                id=1,
                encrypted_webhook_url=encrypt_wecom_webhook_url(
                    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
                ),
                timeout_seconds=45,
                max_retries=3,
                rate_limit_per_minute=15,
                default_mentioned_user_ids=dumps_int_list([2, 1, 2]),
                default_mentioned_list=dumps_string_list(["alice", "alice", "bob"]),
                default_mentioned_mobile_list=dumps_string_list(["13800000000", "13800000000"]),
                default_prompt="",
            )
        )
        db.add_all(
            [
                LocalUser(id=1, username="alice", password_hash="x", display_name="Alice", wecom_mobile="13800000000", enabled=True),
                LocalUser(id=2, username="bob", password_hash="x", display_name="Bob", wecom_mobile="13800000000", enabled=True),
                LocalUser(id=3, username="disabled", password_hash="x", display_name="Disabled", wecom_mobile="13800000000", enabled=False),
            ]
        )
        db.commit()

        settings = load_wecom_robot_settings_from_db(db)

    assert settings.webhook_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
    assert settings.timeout_seconds == 45
    assert settings.max_retries == 3
    assert settings.rate_limit_per_minute == 15
    assert settings.default_mentioned_list == ("alice", "bob")
    assert settings.default_mentioned_mobile_list == ("13800000000",)
    assert settings.default_prompt == ""


def test_send_wecom_robot_test_message_skips_blank_content(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[LocalUser.__table__, WeComRobotSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as db:
        result = send_wecom_robot_test_message(db, "   ")

    assert result == {"status": "skipped", "message": WECOM_TEST_MESSAGE_SKIPPED}


def test_send_wecom_robot_test_message_uses_mentions_when_content_blank(monkeypatch):
    sent: dict[str, object] = {}

    class DummyClient:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def send_text(self, message, *, mentioned_list=None, mentioned_mobile_list=None):
            sent["message"] = message
            sent["mentioned_list"] = mentioned_list
            sent["mentioned_mobile_list"] = mentioned_mobile_list
            return {"status": "ok"}

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[LocalUser.__table__, WeComRobotSetting.__table__])
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("app.wecom_service.load_wecom_robot_settings_from_db", lambda db: object())
    monkeypatch.setattr("app.wecom_service.WeComRobotClient", DummyClient)

    with session_factory() as db:
        db.add(
            WeComRobotSetting(
                id=1,
                default_mentioned_user_ids=dumps_int_list([1]),
                default_mentioned_list=dumps_string_list(["zhangsan"]),
                default_mentioned_mobile_list="[]",
            )
        )
        db.add(LocalUser(id=1, username="alice", password_hash="x", display_name="Alice", wecom_mobile="13800000000", enabled=True))
        db.commit()

        result = send_wecom_robot_test_message(db, "   ")

    assert result == {"status": "mentioned", "message": WECOM_TEST_MENTION_SENT}
    assert sent["message"] == WECOM_TEST_MENTION_CONTENT
    assert sent["mentioned_list"] == ["zhangsan"]
    assert sent["mentioned_mobile_list"] == ["13800000000"]


def test_send_wecom_robot_test_message_trims_content(monkeypatch):
    sent: dict[str, str] = {}

    class DummyClient:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def send_text(self, message):
            sent["message"] = message
            return {"status": "ok"}

    monkeypatch.setattr("app.wecom_service.load_wecom_robot_settings_from_db", lambda db: object())
    monkeypatch.setattr("app.wecom_service.WeComRobotClient", DummyClient)

    result = send_wecom_robot_test_message(object(), "  测试消息  ")

    assert result == {"status": "ok"}
    assert sent["message"] == "测试消息"


def test_validate_wecom_webhook_url_rejects_invalid_url():
    try:
        validate_wecom_webhook_url("https://example.com/webhook")
    except Exception as exc:
        assert "webhook" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_validate_wecom_robot_payload_requires_webhook_when_missing():
    row = WeComRobotSetting(id=1, encrypted_webhook_url=None)
    try:
        _validate_wecom_robot_payload(
            WeComRobotSettingUpdateRequest(
                webhook_url="",
                timeout_seconds=30,
                max_retries=2,
                rate_limit_per_minute=20,
            ),
            row,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 422
        assert getattr(exc, "detail", "") == "webhook_url不能为空"
    else:
        raise AssertionError("expected validation error")


def test_validate_wecom_robot_payload_keeps_existing_webhook_when_blank():
    row = WeComRobotSetting(id=1, encrypted_webhook_url=b"existing")

    data = _validate_wecom_robot_payload(
        WeComRobotSettingUpdateRequest(
            webhook_url="",
            timeout_seconds=30,
            max_retries=2,
            rate_limit_per_minute=20,
            purchase_order_notify_enabled=True,
        ),
        row,
    )

    assert data["webhook_url"] == ""
    assert data["purchase_order_notify_enabled"] is True


def test_render_purchase_order_notice_image_creates_png():
    rows = [
        PurchaseOrderNoticeRow(
            buyer="Alice",
            picking_date="2026-07-07",
            product_name="专辑-CORTIS-GREENGREEN-PB版 蓝",
            daily_order_qty=1,
            stock_qty=0,
            pending_purchase_qty=1,
            exported_at="2026-07-07 12:34:15",
        )
    ]
    image_path = render_purchase_order_notice_image(rows, "PO20260707-001")

    try:
        assert image_path.exists()
        assert image_path.suffix == ".png"
        assert image_path.read_bytes().startswith(b"\x89PNG")
    finally:
        image_path.unlink(missing_ok=True)


def test_render_purchase_order_notice_image_wraps_long_product_name():
    from PIL import Image

    rows = [
        PurchaseOrderNoticeRow(
            buyer="Alice",
            picking_date="2026-07-08",
            product_name=(
                "演示无线充电套装-（底座+充电器+欧插）"
                "-演示商品Max80W TEST黑色 0000000000001"
            ),
            daily_order_qty=1,
            stock_qty=0,
            pending_purchase_qty=1,
            exported_at="2026-07-08 09:11:28",
        )
    ]
    image_path = render_purchase_order_notice_image(rows, "PO20260708-001")

    try:
        with Image.open(image_path) as image:
            assert image.size[0] == sum(TABLE_COLUMN_WIDTHS) + 1
            assert image.size[1] > TITLE_HEIGHT + TABLE_HEADER_HEIGHT + TABLE_ROW_MIN_HEIGHT + 1
    finally:
        image_path.unlink(missing_ok=True)


def test_group_purchase_order_notice_rows_groups_blank_buyer():
    rows = [
        PurchaseOrderNoticeRow(
            buyer="Alice",
            picking_date="2026-07-07",
            product_name="产品A",
            daily_order_qty=1,
            stock_qty=0,
            pending_purchase_qty=1,
            exported_at="2026-07-07 12:34:15",
        ),
        PurchaseOrderNoticeRow(
            buyer="",
            picking_date="2026-07-07",
            product_name="产品B",
            daily_order_qty=2,
            stock_qty=1,
            pending_purchase_qty=1,
            exported_at="2026-07-07 12:34:15",
        ),
        PurchaseOrderNoticeRow(
            buyer="Alice",
            picking_date="2026-07-07",
            product_name="产品C",
            daily_order_qty=3,
            stock_qty=0,
            pending_purchase_qty=3,
            exported_at="2026-07-07 12:34:15",
        ),
    ]

    groups = group_purchase_order_notice_rows(rows)

    assert [(buyer, len(group_rows)) for buyer, group_rows in groups] == [("Alice", 2), ("未填写", 1)]


def test_purchase_order_wecom_notification_mentions_buyer_mobile(monkeypatch, tmp_path):
    image_index = 0
    calls: list[tuple[str, object]] = []

    class DummyDb:
        def get(self, model, row_id):
            return SimpleNamespace(id=row_id, purchase_no="PO20260710-001")

        def close(self):
            calls.append(("close", None))

    class DummyClient:
        def __init__(self, settings):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def send_image(self, image_path):
            calls.append(("image", Path(image_path).name))

        def send_text(self, message, *, mentioned_list=None, mentioned_mobile_list=None, use_default_mentions=True):
            calls.append(
                (
                    "text",
                    {
                        "message": message,
                        "mentioned_list": mentioned_list,
                        "mentioned_mobile_list": mentioned_mobile_list,
                        "use_default_mentions": use_default_mentions,
                    },
                )
            )

    def render_image(rows, purchase_no, *, buyer):
        nonlocal image_index
        image_index += 1
        image_path = tmp_path / f"notice-{image_index}.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake image")
        return image_path

    rows = [
        PurchaseOrderNoticeRow(
            buyer="Alice",
            picking_date="2026-07-10",
            product_name="产品A",
            daily_order_qty=1,
            stock_qty=0,
            pending_purchase_qty=1,
            exported_at="2026-07-10 10:00:00",
            buyer_user_id=1,
            wecom_mobile="13800000000",
        ),
        PurchaseOrderNoticeRow(
            buyer="Bob",
            picking_date="2026-07-10",
            product_name="产品B",
            daily_order_qty=1,
            stock_qty=0,
            pending_purchase_qty=1,
            exported_at="2026-07-10 10:00:00",
            buyer_user_id=2,
            wecom_mobile="",
        ),
    ]
    monkeypatch.setattr(purchase_order_notification_module, "SessionLocal", lambda: DummyDb())
    monkeypatch.setattr(
        purchase_order_notification_module,
        "_get_wecom_setting",
        lambda db: SimpleNamespace(purchase_order_notify_enabled=True, encrypted_webhook_url=b"secret"),
    )
    monkeypatch.setattr(purchase_order_notification_module, "load_wecom_robot_settings_from_db", lambda db: object())
    monkeypatch.setattr(purchase_order_notification_module, "WeComRobotClient", DummyClient)
    monkeypatch.setattr(purchase_order_notification_module, "build_purchase_order_notice_rows", lambda db, purchase_order_id: rows)
    monkeypatch.setattr(purchase_order_notification_module, "render_purchase_order_notice_image", render_image)

    assert send_purchase_order_wecom_notification(99) is True

    assert calls == [
        ("image", "notice-1.png"),
        (
            "text",
            {
                "message": "Alice，你有新的采购任务，请处理",
                "mentioned_list": None,
                "mentioned_mobile_list": ["13800000000"],
                "use_default_mentions": False,
            },
        ),
        ("image", "notice-2.png"),
        ("close", None),
    ]
    assert not (tmp_path / "notice-1.png").exists()
    assert not (tmp_path / "notice-2.png").exists()


def test_wecom_mention_user_option_preserves_mobile_state():
    user = LocalUser(
        id=5,
        username="alice",
        password_hash="x",
        display_name="Alice",
        wecom_mobile="13800000000",
        enabled=True,
    )

    option = _wecom_mention_user_option_dto(user)

    assert option.id == 5
    assert option.display_name == "Alice"
    assert option.wecom_mobile == "13800000000"

    missing_mobile = LocalUser(
        id=6,
        username="bob",
        password_hash="x",
        display_name="",
        wecom_mobile="",
        enabled=True,
    )

    missing_option = _wecom_mention_user_option_dto(missing_mobile)

    assert missing_option.display_name == "bob"
    assert missing_option.wecom_mobile == ""
