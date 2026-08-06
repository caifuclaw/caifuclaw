#!/usr/bin/env python3
# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""Recover labels skipped by the Joom logistics-rule gate for one task run.

The script is deliberately limited to regular Joom online-fulfillment orders
which a scheduled run marked shipped with the unmatched-rule message.  It
excludes FBJ, BSI, overseas-warehouse, and offline-shipping flows.

Run without ``--apply`` to inspect the target set.  ``--apply`` performs the
same Joom online fulfillment path used before the routing regression, creates
the platform and Chinese-label PDFs, and submits both print jobs.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.chinese_label_pdf import generate_chinese_label_pdf  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.label_storage import save_label_pdf  # noqa: E402
from app.models import Order, ScheduledTaskRunOrder  # noqa: E402
from app.order_operation_logs import (  # noqa: E402
    ORDER_LOG_SYSTEM_SOURCE,
    SYSTEM_OPERATOR,
    add_order_operation_logs,
)
from app.order_types import (  # noqa: E402
    order_is_joom_bsi_draft,
    order_is_joom_fbj_warehouse,
    order_is_joom_offline_shipping,
    order_is_overseas_warehouse,
)
from app.pdf_tools import merge_pdf_parts, orient_pdf_bytes  # noqa: E402
from app.print_options import PRINT_PLATFORM_CHINESE_LABEL, label_size_mm_for_platform  # noqa: E402
from app.sync_engine import submit_platform_shipments_and_refresh_logistics  # noqa: E402
from app.task_runner import (  # noqa: E402
    _build_print_job_name,
    _chinese_label_rows_for_orders,
    _ensure_labels_cached,
    _print_setting_page_orientation,
    _printer_setting_map,
    _submit_pdf_to_printer,
)


JOOM_PLATFORMS = ("joom", "joom_logistics", "joomlogistics")
UNMATCHED_PRINT_MESSAGE = "物流规则未匹配，跳过同步物流、打印和采购"
ORDER_STATUS_SHIPPED = "已发货"


def _order_number(row: Order) -> str:
    return row.platform_order_no or row.posting_number or row.platform_order_id or str(row.id)


def _load_candidates(db, run_id: int) -> list[Order]:
    rows = db.scalars(
        select(Order)
        .join(ScheduledTaskRunOrder, ScheduledTaskRunOrder.order_id == Order.id)
        .where(
            ScheduledTaskRunOrder.run_id == run_id,
            ScheduledTaskRunOrder.print_message == UNMATCHED_PRINT_MESSAGE,
            Order.platform.in_(JOOM_PLATFORMS),
            Order.fulfillment_type == "DEFAULT",
            Order.is_overseas_warehouse == False,  # noqa: E712
            Order.logistics_match_status == "unmatched",
            Order.biz_status == ORDER_STATUS_SHIPPED,
            Order.label_printed_at.is_(None),
        )
        .order_by(Order.id)
    ).all()
    return [
        row
        for row in rows
        if not order_is_overseas_warehouse(row)
        and not order_is_joom_fbj_warehouse(row)
        and not order_is_joom_bsi_draft(row)
        and not order_is_joom_offline_shipping(row)
    ]


def _require_printers(db) -> tuple[object, object]:
    settings = _printer_setting_map(db)
    platform_setting = settings.get("joom_logistics")
    chinese_setting = settings.get(PRINT_PLATFORM_CHINESE_LABEL)
    missing = [
        name
        for name, setting in (("joom_logistics", platform_setting), (PRINT_PLATFORM_CHINESE_LABEL, chinese_setting))
        if not setting or not (setting.printer_name or "").strip()
    ]
    if missing:
        raise RuntimeError("Missing enabled label printer settings: " + ", ".join(missing))
    return platform_setting, chinese_setting


async def _recover_and_print(db, rows: list[Order], run_id: int, *, apply: bool) -> None:
    platform_setting, chinese_setting = _require_printers(db)
    print(f"run_id={run_id} candidates={len(rows)}")
    for row in rows:
        print(f"  order_id={row.id} order={_order_number(row)} status={row.biz_status} local={row.local_status}")

    if not apply:
        print("dry-run: no platform fulfillment, PDF generation, or printer submission performed")
        return

    fulfillment = await submit_platform_shipments_and_refresh_logistics(
        db,
        rows,
        eligible_statuses={ORDER_STATUS_SHIPPED},
        preserve_biz_status_on_refresh=True,
    )
    print(
        "fulfillment "
        f"submitted={fulfillment['submitted']} existing={fulfillment['skipped_existing']} "
        f"failed={fulfillment['submit_failed']}"
    )
    if fulfillment["submit_failed"]:
        details = "; ".join(str(error.get("message") or "unknown") for error in fulfillment["errors"])
        raise RuntimeError(f"Joom online fulfillment failed; no labels were printed: {details}")

    missing_tracking = [row for row in rows if not (row.shipment_tracking_number or "").strip()]
    if missing_tracking:
        raise RuntimeError(
            "Joom fulfillment did not return tracking numbers for: "
            + ", ".join(_order_number(row) for row in missing_tracking)
        )

    pdf_map, cached, fetched, failed = await _ensure_labels_cached(db, rows, load_bytes=True)
    print(f"labels cached={cached} fetched={fetched} failed={failed}")
    missing_labels = [row for row in rows if not pdf_map.get(row.id)]
    if missing_labels:
        raise RuntimeError("Missing real Joom label PDF for: " + ", ".join(_order_number(row) for row in missing_labels))

    platform_orientation = _print_setting_page_orientation("joom_logistics", platform_setting)
    platform_pdf = merge_pdf_parts(
        [
            orient_pdf_bytes(
                pdf_map[row.id],
                platform_orientation,
                target_size_mm=label_size_mm_for_platform("joom_logistics"),
            )
            for row in rows
        ]
    )
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    platform_pdf_path, _ = save_label_pdf(
        "system",
        "joom-recovery",
        "joom_logistics",
        f"run-{run_id}-platform-labels-{timestamp}",
        platform_pdf,
    )
    chinese_pdf = generate_chinese_label_pdf(_chinese_label_rows_for_orders(db, rows))
    chinese_pdf_path, _ = save_label_pdf(
        "system",
        "joom-recovery",
        PRINT_PLATFORM_CHINESE_LABEL,
        f"run-{run_id}-chinese-labels-{timestamp}",
        chinese_pdf,
    )

    platform_job = _build_print_job_name("recovery", "joom_logistics", f"run{run_id}")
    submitted, message = _submit_pdf_to_printer(
        platform_pdf_path,
        platform_setting.printer_name.strip(),
        allow_offline_queue=False,
        require_queue_observed=True,
        job_name=platform_job,
        page_orientation=platform_orientation,
        target_size_mm=label_size_mm_for_platform("joom_logistics"),
    )
    print(f"platform_pdf={platform_pdf_path}")
    print(f"platform_print submitted={submitted} message={message}")
    if not submitted:
        raise RuntimeError(f"Joom platform label print submission failed: {message}")

    chinese_orientation = _print_setting_page_orientation(PRINT_PLATFORM_CHINESE_LABEL, chinese_setting)
    chinese_job = _build_print_job_name("recovery", PRINT_PLATFORM_CHINESE_LABEL, f"run{run_id}")
    submitted, message = _submit_pdf_to_printer(
        chinese_pdf_path,
        chinese_setting.printer_name.strip(),
        allow_offline_queue=False,
        require_queue_observed=True,
        job_name=chinese_job,
        page_orientation=chinese_orientation,
        target_size_mm=None,
    )
    print(f"chinese_pdf={chinese_pdf_path}")
    print(f"chinese_print submitted={submitted} message={message}")
    if not submitted:
        raise RuntimeError(f"Chinese label print submission failed: {message}")

    now = datetime.utcnow()
    for row in rows:
        row.label_printed_at = now
        row.updated_at = now
    add_order_operation_logs(
        db,
        rows,
        operation_type="print_label",
        operation_attribute="恢复 Joom 面单和中文标签打印",
        description=lambda order: (
            f"恢复脚本处理：订单 {_order_number(order)} 按 Joom 线上履约生成平台面单和中文标签，"
            f"已提交到 {platform_setting.printer_name.strip()} 与 {chinese_setting.printer_name.strip()}"
        ),
        operator=SYSTEM_OPERATOR,
        source=ORDER_LOG_SYSTEM_SOURCE,
        operated_at=now,
        event_key=lambda order: f"recover_joom_unmatched_labels:run:{run_id}:order:{order.id}",
        extra=lambda order: {
            "script": Path(__file__).name,
            "run_id": run_id,
            "platform_label_pdf": str(platform_pdf_path),
            "chinese_label_pdf": str(chinese_pdf_path),
            "platform_printer": platform_setting.printer_name.strip(),
            "chinese_printer": chinese_setting.printer_name.strip(),
        },
    )
    db.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True, help="Scheduled task run ID containing the skipped Joom orders.")
    parser.add_argument("--apply", action="store_true", help="Perform Joom fulfillment, create PDFs, and submit the print jobs.")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        try:
            rows = _load_candidates(db, args.run_id)
            if not rows:
                print("No unprinted regular Joom unmatched-rule orders found for the specified run.")
                return 0
            await _recover_and_print(db, rows, args.run_id, apply=args.apply)
            if not args.apply:
                db.rollback()
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
