from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from app.database import SessionLocal
from app.models import PlatformAccount
from app.order_outbound_import import run_order_outbound_import
from app.product_models import Product, ProductInventory, ProductShopMapping
from import_product_catalog_full import ImportStats, generate_product_code, read_excel_groups, run_import, unique_values


DEFAULT_EXCEL_NAME = "Order follow up 2026.xlsx"
DEFAULT_SOURCE_DIRS = [
    Path.home() / "demo_data" / "result_data_sync",
    Path.home() / "demo_data" / "result_data_backup",
    Path("./demo_data/result_data_sync"),
    Path("./demo_data/result_data_backup"),
]


def unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        result.append(path.expanduser())
    return result


def latest_matching_excel(source_dirs: list[Path]) -> Path | None:
    for source_dir in unique_paths(source_dirs):
        if source_dir.is_file() and source_dir.exists():
            return source_dir
        if not source_dir.is_dir():
            continue
        exact = source_dir / DEFAULT_EXCEL_NAME
        if exact.exists():
            return exact

    candidates: list[Path] = []
    for source_dir in unique_paths(source_dirs):
        if not source_dir.is_dir():
            continue
        candidates.extend(source_dir.glob("Order follow up 2026*.xlsx"))
    if not candidates:
        return None
    return max((path for path in candidates if path.exists()), key=lambda path: path.stat().st_mtime)


def resolve_excel_path(file_path: Path | None, source_dirs: list[Path]) -> Path:
    if file_path:
        resolved = file_path.expanduser()
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        return resolved

    resolved = latest_matching_excel(source_dirs)
    if resolved:
        return resolved
    searched = ", ".join(str(path) for path in unique_paths(source_dirs))
    raise FileNotFoundError(f"未找到 {DEFAULT_EXCEL_NAME}，已搜索: {searched}")


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def default_log_path(dry_run: bool) -> Path:
    suffix = "dryrun" if dry_run else "apply"
    return ROOT / "logs" / f"product_catalog_update_{timestamp()}_{suffix}.csv"


def default_missing_only_log_path(dry_run: bool) -> Path:
    suffix = "dryrun" if dry_run else "apply"
    return ROOT / "logs" / f"product_catalog_missing_only_{timestamp()}_{suffix}.csv"


def default_outbound_log_path(dry_run: bool) -> Path:
    suffix = "dryrun" if dry_run else "apply"
    return ROOT / "logs" / f"order_outbound_update_{timestamp()}_{suffix}.csv"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_missing_only_import(path: Path, apply: bool, log_path: Path) -> dict:
    stats = ImportStats()
    groups, shop_columns, unresolved_headers, events = read_excel_groups(path, stats)
    created_rows: list[dict] = []
    skipped_rows: list[dict] = []
    mappings_created = 0

    with SessionLocal() as db:
        existing_products = {
            product.internal_name: product
            for product in db.scalars(select(Product)).all()
        }
        used_codes = {code for (code,) in db.execute(select(Product.product_code)).all()}
        max_code = db.scalar(select(func.max(Product.product_code)).where(Product.product_code.like("P________")))
        existing_mappings: dict[tuple[int, str], ProductShopMapping] = {
            (mapping.shop_id, mapping.shop_sku): mapping
            for mapping in db.scalars(
                select(ProductShopMapping).options(
                    joinedload(ProductShopMapping.product),
                    joinedload(ProductShopMapping.shop),
                )
            ).all()
        }
        missing_groups = [(name, group) for name, group in groups.items() if name not in existing_products]

        for name, group in missing_groups:
            conflicts = []
            mapping_items = []
            for shop_id, sku_list in group.mappings.items():
                shop = db.get(PlatformAccount, shop_id)
                for sku in sku_list:
                    existing = existing_mappings.get((shop_id, sku))
                    if existing and existing.product and existing.product.internal_name != name:
                        conflicts.append(
                            {
                                "shop_id": shop_id,
                                "shop": shop.display_name if shop else str(shop_id),
                                "sku": sku,
                                "existing_product": existing.product.internal_name,
                            }
                        )
                    else:
                        mapping_items.append((shop_id, shop, sku))

            if conflicts:
                skipped_rows.append(
                    {
                        "row": group.first_row,
                        "product": name,
                        "reason": "sku_conflict",
                        "detail": "; ".join(
                            f"{item['shop']} {item['sku']} -> {item['existing_product']}"
                            for item in conflicts
                        ),
                    }
                )
                continue

            field_values = {}
            field_conflicts = []
            for field_name, values in group.fields.items():
                distinct_values = unique_values(values)
                if values and len(distinct_values) <= 1:
                    field_values[field_name] = values[-1].value
                elif values:
                    field_conflicts.append((field_name, distinct_values))
            if field_conflicts:
                skipped_rows.append(
                    {
                        "row": group.first_row,
                        "product": name,
                        "reason": "field_conflict",
                        "detail": "; ".join(
                            f"{field}: {' | '.join(str(value) for value in values)}"
                            for field, values in field_conflicts
                        ),
                    }
                )
                continue

            product_code = generate_product_code(max_code, used_codes)
            now = utc_now()
            product_id = None
            if apply:
                product = Product(
                    product_code=product_code,
                    internal_name=name,
                    cost=field_values.get("cost"),
                    weight=field_values.get("weight"),
                    safety_stock=field_values.get("safety_stock"),
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(product)
                db.flush()
                product_id = product.id
                added_mappings = []
                for shop_id, shop, sku in mapping_items:
                    mapping = ProductShopMapping(
                        product_id=product.id,
                        shop_id=shop_id,
                        shop_sku=sku,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(mapping)
                    existing_mappings[(shop_id, sku)] = mapping
                    mappings_created += 1
                    added_mappings.append(f"{shop.display_name if shop else shop_id}:{sku}")
                db.add(
                    ProductInventory(
                        product_id=product.id,
                        product_name=product.internal_name,
                        stock_qty=0,
                        last_count_qty=0,
                        remark="",
                        updated_by="catalog_import_missing_only",
                        created_at=now,
                        updated_at=now,
                    )
                )
                existing_products[name] = product
            else:
                added_mappings = [f"{shop.display_name if shop else shop_id}:{sku}" for shop_id, shop, sku in mapping_items]
                mappings_created += len(mapping_items)

            created_rows.append(
                {
                    "id": product_id or "",
                    "product_code": product_code,
                    "product": name,
                    "cost": field_values.get("cost"),
                    "weight": field_values.get("weight"),
                    "safety_stock": field_values.get("safety_stock"),
                    "mappings": "; ".join(added_mappings),
                }
            )

        if apply:
            db.commit()
        else:
            db.rollback()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["type", "id", "product_code", "row", "product", "cost", "weight", "safety_stock", "mappings", "reason", "detail"])
        for row in created_rows:
            writer.writerow([
                "created" if apply else "would_create",
                row["id"],
                row["product_code"],
                "",
                row["product"],
                row["cost"] or "",
                row["weight"] or "",
                row["safety_stock"] if row["safety_stock"] is not None else "",
                row["mappings"],
                "",
                "",
            ])
        for row in skipped_rows:
            writer.writerow(["skipped", "", "", row["row"], row["product"], "", "", "", "", row["reason"], row["detail"]])
        writer.writerow([])
        writer.writerow(["summary", "excel_unique_products", stats.unique_product_names])
        writer.writerow(["summary", "missing_by_name_before_import", len(created_rows) + len(skipped_rows)])
        writer.writerow(["summary", "created_products", len(created_rows) if apply else 0])
        writer.writerow(["summary", "would_create_products", len(created_rows)])
        writer.writerow(["summary", "mappings_created", mappings_created if apply else 0])
        writer.writerow(["summary", "would_create_mappings", mappings_created])
        writer.writerow(["summary", "inventory_created", len(created_rows) if apply else 0])
        writer.writerow(["summary", "skipped_conflicts", sum(1 for row in skipped_rows if row["reason"] == "sku_conflict")])
        writer.writerow(["summary", "skipped_field_conflicts", sum(1 for row in skipped_rows if row["reason"] == "field_conflict")])
        writer.writerow(["summary", "resolved_shop_columns", "; ".join(f"{idx + 1}:{shop.display_name}" for idx, shop in sorted(shop_columns.items()))])
        writer.writerow(["summary", "unresolved_headers", "; ".join(unresolved_headers)])

    result = {
        "mode": "apply" if apply else "dry-run",
        "rows_seen": stats.rows_seen,
        "excel_unique_products": stats.unique_product_names,
        "missing_by_name_before_import": len(created_rows) + len(skipped_rows),
        "created_products": len(created_rows) if apply else 0,
        "would_create_products": len(created_rows),
        "mappings_created": mappings_created if apply else 0,
        "would_create_mappings": mappings_created,
        "inventory_created": len(created_rows) if apply else 0,
        "skipped_conflicts": sum(1 for row in skipped_rows if row["reason"] == "sku_conflict"),
        "skipped_field_conflicts": sum(1 for row in skipped_rows if row["reason"] == "field_conflict"),
        "log": str(log_path),
    }
    print("模式:", "missing-only 正式写入" if apply else "missing-only dry-run 未写入")
    print("读取行数:", stats.rows_seen)
    print("唯一产品中文名:", stats.unique_product_names)
    print("缺失产品:", result["missing_by_name_before_import"])
    print("新增产品:", result["created_products"])
    print("可新增产品:", result["would_create_products"])
    print("新增映射:", result["mappings_created"])
    print("跳过 SKU 冲突:", result["skipped_conflicts"])
    print("跳过字段冲突:", result["skipped_field_conflicts"])
    print("日志:", log_path)
    return result


def print_json(title: str, rows: list[dict]) -> None:
    print(title)
    if not rows:
        print("[]")
        return
    print(json.dumps(rows, ensure_ascii=False, default=str, indent=2))


def verify_skus(skus: list[str]) -> None:
    if not skus:
        return
    with SessionLocal() as db:
        rows = db.execute(
            text(
                """
                select
                    psm.shop_sku,
                    pa.platform,
                    pa.account_id,
                    pa.display_name as shop_name,
                    p.product_code,
                    p.internal_name,
                    p.enabled
                from product_shop_mappings psm
                join platform_accounts pa on pa.id = psm.shop_id
                join products p on p.id = psm.product_id
                where psm.shop_sku = any(:skus)
                order by psm.shop_sku, pa.id
                """
            ),
            {"skus": skus},
        ).mappings().all()
    print_json("SKU 匹配复查:", [dict(row) for row in rows])


def verify_orders(order_numbers: list[str]) -> None:
    if not order_numbers:
        return
    with SessionLocal() as db:
        rows = db.execute(
            text(
                """
                select
                    o.platform_order_no,
                    o.posting_number,
                    o.platform,
                    o.shop_name,
                    oi.sku,
                    oi.platform_product_name,
                    p.product_code,
                    p.internal_name as product_name
                from orders o
                join order_items oi on oi.order_id = o.id
                left join platform_accounts pa
                    on pa.platform = o.platform
                    and pa.account_id = coalesce(nullif(o.shop_id, ''), o.account_id)
                left join product_shop_mappings psm
                    on psm.shop_id = pa.id
                    and psm.shop_sku = oi.sku
                left join products p on p.id = psm.product_id
                where o.platform_order_no = any(:order_numbers)
                    or o.posting_number = any(:order_numbers)
                order by o.id, oi.id
                """
            ),
            {"order_numbers": order_numbers},
        ).mappings().all()
    print_json("订单中文名称复查:", [dict(row) for row in rows])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="更新 Order follow up 产品目录，并在 missing-only 模式同步订单出库")
    parser.add_argument("--file", type=Path, default=None, help="指定 Order follow up Excel 文件；不传则自动搜索最新文件")
    parser.add_argument(
        "--source-dir",
        type=Path,
        action="append",
        default=[],
        help="自动搜索目录，可重复传；默认搜索 demo_data/result_data_sync 和备份目录",
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览导入结果，不写入数据库")
    parser.add_argument("--missing-only", action="store_true", help="只新增系统缺失产品；跳过 SKU 已绑定其他产品的名称变体")
    parser.add_argument(
        "--keep-existing-shop-mappings",
        action="store_true",
        help="全量导入时不删除源表店铺列中已不存在的旧 SKU 映射",
    )
    parser.add_argument(
        "--field-conflict-policy",
        choices=("latest", "first", "keep-existing"),
        default="latest",
        help="同一中文名基础字段多值时的处理策略",
    )
    parser.add_argument("--log", type=Path, default=None, help="导入日志 CSV 路径；不传则自动按时间命名")
    parser.add_argument("--outbound-log", type=Path, default=None, help="订单出库更新日志；missing-only 模式下生效")
    parser.add_argument("--skip-outbound-update", action="store_true", help="missing-only 模式下跳过订单出库更新")
    parser.add_argument("--sku", action="append", default=[], help="导入后复查指定 SKU，可重复传")
    parser.add_argument("--order-no", action="append", default=[], help="导入后复查指定订单号/发货单号，可重复传")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dirs = [*args.source_dir, *DEFAULT_SOURCE_DIRS]
    excel_path = resolve_excel_path(args.file, source_dirs)

    print(f"Excel: {excel_path}")
    if args.missing_only:
        log_path = args.log or default_missing_only_log_path(args.dry_run)
        result = run_missing_only_import(path=excel_path, apply=not args.dry_run, log_path=log_path)
        print("统计:", json.dumps(result, ensure_ascii=False, default=str))
        if not args.skip_outbound_update:
            outbound_log_path = args.outbound_log or default_outbound_log_path(args.dry_run)
            outbound_stats = run_order_outbound_import(
                excel_path,
                apply=not args.dry_run,
                log_path=outbound_log_path,
            )
            print("订单出库统计:", json.dumps(asdict(outbound_stats), ensure_ascii=False, default=str))
    else:
        log_path = args.log or default_log_path(args.dry_run)
        stats = run_import(
            path=excel_path,
            apply=not args.dry_run,
            log_path=log_path,
            field_conflict_policy=args.field_conflict_policy,
            prune_shop_mappings=not args.keep_existing_shop_mappings,
        )
        print("统计:", json.dumps(asdict(stats), ensure_ascii=False))
    verify_skus(args.sku)
    verify_orders(args.order_no)


if __name__ == "__main__":
    main()
