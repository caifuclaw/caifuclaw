from __future__ import annotations

import logging
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, asc, func, or_, select, text
from sqlalchemy.orm import Session

from common.wecom_robot import WeComRobotClient, WeComRobotError

from .database import SessionLocal
from .models import LocalUser, Order
from .product_models import ProductInventory, PurchaseOrder, PurchaseOrderItem, PurchaseOrderSource
from .wecom_service import load_wecom_robot_settings_from_db


logger = logging.getLogger(__name__)

LOCAL_TIME_OFFSET = timedelta(hours=8)
TABLE_HEADERS = ["配货日", "产品名称", "采购数量（当日来单）", "库存数", "待采购数量", "导出时间"]
TABLE_COLUMN_WIDTHS = [120, 680, 240, 130, 160, 240]
TABLE_HEADER_BG = "#3f70bf"
TABLE_TEXT = "#000000"
TABLE_BORDER = "#000000"
TABLE_ROW_BG = "#ffffff"
TITLE_HEIGHT = 48
TABLE_HEADER_HEIGHT = 44
TABLE_ROW_MIN_HEIGHT = 42
TABLE_CELL_PADDING_X = 8
TABLE_CELL_PADDING_Y = 8
TABLE_LINE_GAP = 4
PURCHASE_ORDER_TASK_MESSAGE = "你有新的采购任务，请处理"


@dataclass(frozen=True)
class PurchaseOrderNoticeRow:
    buyer: str
    picking_date: str
    product_name: str
    daily_order_qty: int
    stock_qty: int
    pending_purchase_qty: int
    exported_at: str
    buyer_user_id: int | None = None
    wecom_mobile: str = ""


def enqueue_purchase_order_wecom_notification(purchase_order_id: int, *, source: str = "") -> None:
    if not purchase_order_id:
        return
    thread = threading.Thread(
        target=send_purchase_order_wecom_notification,
        args=(purchase_order_id,),
        kwargs={"source": source},
        name=f"purchase-order-wecom-{purchase_order_id}",
        daemon=True,
    )
    try:
        thread.start()
    except Exception:
        logger.exception("Failed to enqueue purchase order WeCom notification: %s", purchase_order_id)


def send_purchase_order_wecom_notification(purchase_order_id: int, *, source: str = "") -> bool:
    db = SessionLocal()
    image_paths: list[Path] = []
    try:
        setting = _get_wecom_setting(db)
        if not setting or not bool(getattr(setting, "purchase_order_notify_enabled", False)):
            return False
        if not getattr(setting, "encrypted_webhook_url", None):
            return False

        purchase = db.get(PurchaseOrder, purchase_order_id)
        if not purchase:
            logger.warning("Skip purchase order WeCom notification; purchase order not found: %s", purchase_order_id)
            return False

        rows = build_purchase_order_notice_rows(db, purchase_order_id)
        if not rows:
            logger.info("Skip purchase order WeCom notification; no rows for purchase order %s", purchase_order_id)
            return False

        settings = load_wecom_robot_settings_from_db(db)
        sent_count = 0
        with WeComRobotClient(settings) as client:
            for buyer, buyer_rows in group_purchase_order_notice_rows(rows):
                image_path: Path | None = None
                try:
                    image_path = render_purchase_order_notice_image(buyer_rows, purchase.purchase_no, buyer=buyer)
                    image_paths.append(image_path)
                    client.send_image(image_path)
                    sent_count += 1
                    mentioned_mobile_list = _mentioned_mobile_list_for_notice_rows(buyer_rows)
                    if mentioned_mobile_list:
                        try:
                            client.send_text(
                                f"{_buyer_label(buyer)}，{PURCHASE_ORDER_TASK_MESSAGE}",
                                mentioned_mobile_list=mentioned_mobile_list,
                                use_default_mentions=False,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Purchase order WeCom notification mention failed: purchase_order_id=%s purchase_no=%s buyer=%s mobile_count=%s error=%s",
                                purchase_order_id,
                                purchase.purchase_no,
                                buyer,
                                len(mentioned_mobile_list),
                                exc,
                            )
                except Exception as exc:
                    logger.warning(
                        "Purchase order WeCom notification image failed: purchase_order_id=%s purchase_no=%s buyer=%s error=%s",
                        purchase_order_id,
                        purchase.purchase_no,
                        buyer,
                        exc,
                    )
        logger.info(
            "Sent purchase order WeCom notification: purchase_order_id=%s purchase_no=%s source=%s images=%s",
            purchase_order_id,
            purchase.purchase_no,
            source,
            sent_count,
        )
        return sent_count > 0
    except WeComRobotError as exc:
        logger.warning("Purchase order WeCom notification skipped/failed for %s: %s", purchase_order_id, exc)
        return False
    except Exception:
        logger.exception("Purchase order WeCom notification failed for %s", purchase_order_id)
        return False
    finally:
        db.close()
        for image_path in image_paths:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                logger.debug("Failed to remove purchase order notice image: %s", image_path, exc_info=True)


def build_purchase_order_notice_rows(db: Session, purchase_order_id: int) -> list[PurchaseOrderNoticeRow]:
    exported_at = _local_now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(_purchase_order_notice_stmt(purchase_order_id)).all()
    return [
        PurchaseOrderNoticeRow(
            buyer=(row.buyer or "").strip(),
            buyer_user_id=int(row.buyer_user_id) if row.buyer_user_id is not None else None,
            wecom_mobile=(row.wecom_mobile or "").strip(),
            picking_date=_date_iso(row.picking_date or row.purchase_date) or "",
            product_name=row.product_name or "",
            daily_order_qty=int(row.daily_order_qty or 0),
            stock_qty=int(row.stock_qty or 0),
            pending_purchase_qty=int(
                row.pending_purchase_qty
                if row.pending_purchase_qty is not None
                else int(row.daily_order_qty or 0) - int(row.stock_qty or 0)
            ),
            exported_at=exported_at,
        )
        for row in rows
    ]


def group_purchase_order_notice_rows(rows: list[PurchaseOrderNoticeRow]) -> list[tuple[str, list[PurchaseOrderNoticeRow]]]:
    groups: list[tuple[str, list[PurchaseOrderNoticeRow]]] = []
    group_index: dict[str, int] = {}
    for row in rows:
        buyer = _buyer_label(row.buyer)
        if buyer not in group_index:
            group_index[buyer] = len(groups)
            groups.append((buyer, []))
        groups[group_index[buyer]][1].append(row)
    return groups


def render_purchase_order_notice_image(
    rows: list[PurchaseOrderNoticeRow],
    purchase_no: str = "",
    *,
    buyer: str = "",
) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render purchase order notice images.") from exc

    font_regular = _load_font(ImageFont, 20)
    font_bold = _load_font(ImageFont, 22, bold=True)
    total_width = sum(TABLE_COLUMN_WIDTHS) + 1
    measure_image = Image.new("RGB", (1, 1), TABLE_ROW_BG)
    measure_draw = ImageDraw.Draw(measure_image)
    product_column_width = TABLE_COLUMN_WIDTHS[1]
    product_inner_width = max(1, product_column_width - TABLE_CELL_PADDING_X * 2)
    product_line_height = max(1, _text_height(measure_draw, "Ag中文", font_regular))
    product_lines_by_row = [
        _wrap_text(measure_draw, row.product_name, font_regular, product_inner_width)
        for row in rows
    ]
    row_heights = [
        max(
            TABLE_ROW_MIN_HEIGHT,
            TABLE_CELL_PADDING_Y * 2 + len(lines) * product_line_height + max(0, len(lines) - 1) * TABLE_LINE_GAP,
        )
        for lines in product_lines_by_row
    ]
    total_height = TITLE_HEIGHT + TABLE_HEADER_HEIGHT + sum(row_heights) + 1
    image = Image.new("RGB", (total_width, total_height), TABLE_ROW_BG)
    draw = ImageDraw.Draw(image)

    title_text = f"采购单：{purchase_no or '-'}    采购人：{_buyer_label(buyer)}"
    draw.rectangle((0, 0, total_width, TITLE_HEIGHT), fill=TABLE_HEADER_BG, outline=TABLE_BORDER, width=1)
    _draw_centered_text(draw, (0, 0, total_width, TITLE_HEIGHT), title_text, font_bold, fill="#ffffff")

    x = 0
    for header, width in zip(TABLE_HEADERS, TABLE_COLUMN_WIDTHS, strict=True):
        draw.rectangle(
            (x, TITLE_HEIGHT, x + width, TITLE_HEIGHT + TABLE_HEADER_HEIGHT),
            fill=TABLE_HEADER_BG,
            outline=TABLE_BORDER,
            width=1,
        )
        _draw_centered_text(
            draw,
            (x, TITLE_HEIGHT, x + width, TITLE_HEIGHT + TABLE_HEADER_HEIGHT),
            header,
            font_bold,
            fill="#ffffff",
        )
        x += width

    y = TITLE_HEIGHT + TABLE_HEADER_HEIGHT
    for row, row_height, product_lines in zip(rows, row_heights, product_lines_by_row, strict=True):
        values = [
            row.picking_date,
            row.product_name,
            str(row.daily_order_qty),
            str(row.stock_qty),
            str(row.pending_purchase_qty),
            row.exported_at,
        ]
        x = 0
        for column_index, (value, width) in enumerate(zip(values, TABLE_COLUMN_WIDTHS, strict=True)):
            draw.rectangle((x, y, x + width, y + row_height), fill=TABLE_ROW_BG, outline=TABLE_BORDER, width=1)
            if column_index == 1:
                block_height = (
                    len(product_lines) * product_line_height
                    + max(0, len(product_lines) - 1) * TABLE_LINE_GAP
                )
                text_y = y + max(TABLE_CELL_PADDING_Y, (row_height - block_height) / 2)
                for line in product_lines:
                    draw.text((x + TABLE_CELL_PADDING_X, text_y), line, font=font_regular, fill=TABLE_TEXT)
                    text_y += product_line_height + TABLE_LINE_GAP
            else:
                _draw_centered_text(draw, (x, y, x + width, y + row_height), str(value), font_regular, fill=TABLE_TEXT)
            x += width
        y += row_height

    safe_purchase_no = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in purchase_no or "purchase-order")
    safe_buyer = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in _buyer_label(buyer))
    output_path = Path(tempfile.gettempdir()) / (
        f"{safe_purchase_no}-{safe_buyer}-wecom-notice-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.png"
    )
    image.save(output_path, format="PNG", optimize=True)
    return output_path


def _purchase_order_notice_stmt(purchase_order_id: int):
    purchase_date_expr = func.coalesce(PurchaseOrder.purchase_date, func.date(PurchaseOrder.created_at))
    picking_date_expr = func.date(Order.picking_at + text("INTERVAL '8 hours'"))
    daily_qty_expr = func.coalesce(func.sum(PurchaseOrderSource.quantity), 0)
    stock_qty_expr = func.coalesce(ProductInventory.stock_qty, 0)
    inventory_join = or_(
        and_(PurchaseOrderItem.product_id.isnot(None), ProductInventory.product_id == PurchaseOrderItem.product_id),
        and_(PurchaseOrderItem.product_id.is_(None), ProductInventory.product_name == PurchaseOrderItem.product_name),
    )
    return (
        select(
            purchase_date_expr.label("purchase_date"),
            picking_date_expr.label("picking_date"),
            PurchaseOrderItem.buyer.label("buyer"),
            PurchaseOrderItem.buyer_user_id.label("buyer_user_id"),
            LocalUser.wecom_mobile.label("wecom_mobile"),
            PurchaseOrderItem.product_name.label("product_name"),
            daily_qty_expr.label("daily_order_qty"),
            stock_qty_expr.label("stock_qty"),
            (daily_qty_expr - stock_qty_expr).label("pending_purchase_qty"),
        )
        .select_from(PurchaseOrder)
        .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
        .outerjoin(
            LocalUser,
            and_(
                LocalUser.id == PurchaseOrderItem.buyer_user_id,
                LocalUser.enabled.is_(True),
            ),
        )
        .join(
            PurchaseOrderSource,
            and_(
                PurchaseOrderSource.purchase_order_id == PurchaseOrder.id,
                PurchaseOrderSource.purchase_order_item_id == PurchaseOrderItem.id,
            ),
        )
        .join(Order, Order.id == PurchaseOrderSource.order_id)
        .outerjoin(ProductInventory, inventory_join)
        .where(PurchaseOrder.id == purchase_order_id)
        .group_by(
            PurchaseOrder.id,
            PurchaseOrderItem.id,
            purchase_date_expr,
            picking_date_expr,
            PurchaseOrderItem.product_id,
            ProductInventory.stock_qty,
            PurchaseOrderItem.buyer,
            PurchaseOrderItem.buyer_user_id,
            LocalUser.wecom_mobile,
            PurchaseOrderItem.product_name,
        )
        .order_by(asc(PurchaseOrderItem.buyer), asc(picking_date_expr), asc(PurchaseOrderItem.product_name), asc(PurchaseOrderItem.id))
    )


def _get_wecom_setting(db: Session):
    from .wecom_service import get_wecom_robot_setting

    return get_wecom_robot_setting(db)


def _local_now() -> datetime:
    return datetime.utcnow() + LOCAL_TIME_OFFSET


def _date_iso(value) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return (value + LOCAL_TIME_OFFSET).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _buyer_label(value: str | None) -> str:
    buyer = " ".join(str(value or "").replace("\u3000", " ").split()).strip()
    return buyer or "未填写"


def _mentioned_mobile_list_for_notice_rows(rows: list[PurchaseOrderNoticeRow]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for row in rows:
        mobile = (row.wecom_mobile or "").strip()
        if not mobile or mobile in seen:
            continue
        seen.add(mobile)
        result.append(mobile)
    return result


def _load_font(ImageFont, size: int, *, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            if candidate and Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_centered_text(draw, box: tuple[int, int, int, int], text_value: str, font, *, fill: str) -> None:
    text_value = str(text_value or "")
    text_width = _text_width(draw, text_value, font)
    text_height = _text_height(draw, text_value, font)
    x1, y1, x2, y2 = box
    draw.text(
        (x1 + max(0, (x2 - x1 - text_width) / 2), y1 + max(0, (y2 - y1 - text_height) / 2)),
        text_value,
        font=font,
        fill=fill,
    )


def _wrap_text(draw, text_value: str, font, max_width: int) -> list[str]:
    value = str(text_value or "")
    if not value:
        return [""]
    lines: list[str] = []
    current = ""
    for char in value:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = f"{current}{char}"
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    lines.append(current)
    return lines


def _text_width(draw, text_value: str, font) -> int:
    bbox = draw.textbbox((0, 0), text_value, font=font)
    return int(bbox[2] - bbox[0])


def _text_height(draw, text_value: str, font) -> int:
    bbox = draw.textbbox((0, 0), text_value or "Ag", font=font)
    return int(bbox[3] - bbox[1])
