"""
数据库索引优化迁移脚本
为订单列表查询添加复合索引，提升查询性能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database import engine


def create_indexes():
    """创建优化索引"""
    indexes = [
        """
        CREATE EXTENSION IF NOT EXISTS pg_trgm
        """,

        # 复合索引：优化订单列表查询（状态 + 平台 + 付款时间排序）
        """
        CREATE INDEX IF NOT EXISTS idx_order_status_platform_payment
        ON orders (biz_status, platform, payment_at)
        """,

        # 复合索引：优化店铺维度的订单查询
        """
        CREATE INDEX IF NOT EXISTS idx_order_shop_payment
        ON orders (shop_id, payment_at)
        """,

        # 复合索引：优化按付款时间降序的列表查询
        """
        CREATE INDEX IF NOT EXISTS idx_order_payment_created
        ON orders (payment_at DESC, created_at DESC)
        """,

        # 复合索引：优化搜索订单编号（支持 ILIKE 查询）
        """
        CREATE INDEX IF NOT EXISTS idx_order_search_ids
        ON orders (posting_number, platform_order_no, platform_order_id)
        """,

        # 工作台：优化付款日期范围、店铺销售和月销售聚合
        """
        CREATE INDEX IF NOT EXISTS idx_order_dashboard_payment_id
        ON orders (payment_at, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_dashboard_payment_shop
        ON orders (payment_at, platform, shop_id, shop_name)
        """,

        # 工作台：优化待发/配货风险统计
        """
        CREATE INDEX IF NOT EXISTS idx_order_dashboard_biz_deadline
        ON orders (biz_status, dispatch_deadline_at, shipping_deadline_at)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_dashboard_pending_payment
        ON orders (biz_status, payment_at)
        WHERE biz_status IN ('待处理', '配货中')
        """,

        # 工作台：优化 SKU 与订单明细聚合
        """
        CREATE INDEX IF NOT EXISTS idx_order_items_dashboard_order_quantity
        ON order_items (order_id, quantity)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_items_dashboard_order_currency
        ON order_items (order_id, id, currency)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_items_sku_trgm
        ON order_items USING gin (sku gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_items_platform_product_name_trgm
        ON order_items USING gin (platform_product_name gin_trgm_ops)
        """,

        # 工作台：优化按币种寻找最近汇率
        """
        CREATE INDEX IF NOT EXISTS idx_exchange_rates_dashboard_currency_date
        ON exchange_rates (currency_code, rate_date DESC, updated_at DESC)
        """,

        # 订单列表：优化状态/平台筛选后的付款时间排序分页
        """
        CREATE INDEX IF NOT EXISTS idx_order_list_status_payment_page
        ON orders (biz_status, payment_at DESC, created_at DESC, updated_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_list_platform_payment_page
        ON orders (platform, payment_at DESC, created_at DESC, updated_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_list_payment_page
        ON orders (payment_at DESC, created_at DESC, updated_at DESC, id DESC)
        """,

        # 订单汇总表：先按已配货订单分页，再补充明细
        """
        CREATE INDEX IF NOT EXISTS idx_order_summary_picking_payment_page
        ON orders (picking_at, payment_at DESC, created_at DESC, updated_at DESC, id DESC)
        WHERE picking_at IS NOT NULL
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_summary_customer_history
        ON orders (shop_id, buyer_id, platform_created_at, id)
        WHERE buyer_id IS NOT NULL AND buyer_id <> ''
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_order_items_order_id_id
        ON order_items (order_id, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_shipments_order_id_id
        ON shipments (order_id, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_label_files_shipment_id_id
        ON label_files (shipment_id, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_success_order_scanned
        ON outbound_scan_records (order_id, scanned_at)
        WHERE result = 'success'
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_platform_accounts_platform_account
        ON platform_accounts (platform, account_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_product_shop_mappings_shop_sku_product
        ON product_shop_mappings (shop_id, shop_sku, product_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_product_shop_mappings_product_shop
        ON product_shop_mappings (product_id, shop_id, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_products_enabled_updated_id
        ON products (enabled, updated_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_products_updated_id
        ON products (updated_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_order_sources_order_item_purchase
        ON purchase_order_sources (order_item_id, purchase_order_id)
        """,

        # 平台接口日志：优化日志汇总、明细分页、关键字模糊搜索
        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_created_id
        ON api_request_logs (created_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_filters_created
        ON api_request_logs (platform, operation, status, created_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_log_date_group
        ON api_request_logs (log_date, platform, account_id, operation)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_account_created
        ON api_request_logs (account_id, created_at DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_url_trgm
        ON api_request_logs USING gin (url gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_account_trgm
        ON api_request_logs USING gin (account_id gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_operation_trgm
        ON api_request_logs USING gin (operation gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_api_request_logs_error_trgm
        ON api_request_logs USING gin (error_message gin_trgm_ops)
        """,

        # 库存和产品：优化库存分页、库存状态和产品模糊搜索
        """
        CREATE INDEX IF NOT EXISTS idx_product_inventory_product_id_id
        ON product_inventory (product_id, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_product_inventory_stock_product
        ON product_inventory (stock_qty, product_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_product_inventory_product_name_trgm
        ON product_inventory USING gin (product_name gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_products_product_code_trgm
        ON products USING gin (product_code gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_products_internal_name_trgm
        ON products USING gin (internal_name gin_trgm_ops)
        """,

        # 采购：优化采购单列表、采购明细关联和筛选
        """
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_created_id
        ON purchase_orders (created_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_purchase_date_created
        ON purchase_orders (purchase_date, created_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_purchase_no_trgm
        ON purchase_orders USING gin (purchase_no gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_order_items_purchase_order_id_id
        ON purchase_order_items (purchase_order_id, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_order_items_product_name_trgm
        ON purchase_order_items USING gin (product_name gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_order_items_buyer_trgm
        ON purchase_order_items USING gin (buyer gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purchase_order_sources_purchase_item_order
        ON purchase_order_sources (purchase_order_id, purchase_order_item_id, order_id)
        """,

        # 出库扫码：优化记录分页、结果筛选和关键字模糊搜索
        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_scanned_page
        ON outbound_scan_records (scanned_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_result_scanned
        ON outbound_scan_records (result, scanned_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_platform_scanned
        ON outbound_scan_records (platform, scanned_at DESC, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_tracking_trgm
        ON outbound_scan_records USING gin (tracking_number gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_shop_name_trgm
        ON outbound_scan_records USING gin (shop_name gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_platform_order_no_trgm
        ON outbound_scan_records USING gin (platform_order_no gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_posting_number_trgm
        ON outbound_scan_records USING gin (posting_number gin_trgm_ops)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_outbound_scan_scanned_by_trgm
        ON outbound_scan_records USING gin (scanned_by gin_trgm_ops)
        """,

        # 定时任务日志：优化运行记录、步骤和订单明细加载
        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_task_runs_task_id_id
        ON scheduled_task_runs (scheduled_task_id, id DESC)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_task_run_steps_run_id_id
        ON scheduled_task_run_steps (run_id, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_task_run_orders_run_id_id
        ON scheduled_task_run_orders (run_id, id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_task_run_orders_run_reprint_id
        ON scheduled_task_run_orders (run_id, needs_reprint, id)
        """,
    ]

    print("开始创建数据库索引...")

    with engine.connect() as conn:
        for idx, sql in enumerate(indexes, 1):
            # 提取索引名称
            index_name = "pg_trgm extension"
            for line in sql.split('\n'):
                if 'idx_' in line or 'pg_trgm' in line:
                    index_name = line.strip()
                    break
            print(f"[{idx}/{len(indexes)}] 创建索引: {index_name}")
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"  ✓ 成功")
            except Exception as e:
                print(f"  ⚠ 跳过或失败: {e}")
                conn.rollback()

    print("\n索引创建完成！")


def analyze_tables():
    """分析表以更新统计信息"""
    print("\n分析表统计信息...")

    with engine.connect() as conn:
        conn.execute(text("ANALYZE orders"))
        conn.execute(text("ANALYZE order_items"))
        conn.execute(text("ANALYZE exchange_rates"))
        conn.execute(text("ANALYZE shipments"))
        conn.execute(text("ANALYZE label_files"))
        conn.execute(text("ANALYZE outbound_scan_records"))
        conn.execute(text("ANALYZE platform_accounts"))
        conn.execute(text("ANALYZE products"))
        conn.execute(text("ANALYZE product_inventory"))
        conn.execute(text("ANALYZE product_shop_mappings"))
        conn.execute(text("ANALYZE api_request_logs"))
        conn.execute(text("ANALYZE purchase_orders"))
        conn.execute(text("ANALYZE purchase_order_items"))
        conn.execute(text("ANALYZE purchase_order_sources"))
        conn.execute(text("ANALYZE scheduled_task_runs"))
        conn.execute(text("ANALYZE scheduled_task_run_steps"))
        conn.execute(text("ANALYZE scheduled_task_run_orders"))
        conn.commit()

    print("✓ 表统计信息更新完成")


def show_index_stats():
    """显示索引统计信息"""
    print("\n当前索引统计信息:")

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                indexname,
                tablename,
                pg_size_pretty(pg_relation_size(indexname::regclass)) as size
            FROM pg_indexes
            WHERE tablename IN (
                'orders',
                'order_items',
                'exchange_rates',
                'shipments',
                'label_files',
                'outbound_scan_records',
                'platform_accounts',
                'products',
                'product_inventory',
                'product_shop_mappings',
                'purchase_orders',
                'purchase_order_items',
                'purchase_order_sources',
                'api_request_logs',
                'scheduled_task_runs',
                'scheduled_task_run_steps',
                'scheduled_task_run_orders'
            )
            AND (
                indexname LIKE 'idx_order%'
                OR indexname LIKE 'idx_api_request_logs%'
                OR indexname LIKE 'idx_exchange_rates_dashboard%'
                OR indexname LIKE 'idx_shipments_order_id_id%'
                OR indexname LIKE 'idx_label_files_shipment_id_id%'
                OR indexname LIKE 'idx_outbound_scan_success_order_scanned%'
                OR indexname LIKE 'idx_outbound_scan_%'
                OR indexname LIKE 'idx_platform_accounts_platform_account%'
                OR indexname LIKE 'idx_products_enabled_updated_id%'
                OR indexname LIKE 'idx_products_updated_id%'
                OR indexname LIKE 'idx_products_product_code_trgm%'
                OR indexname LIKE 'idx_products_internal_name_trgm%'
                OR indexname LIKE 'idx_product_inventory_%'
                OR indexname LIKE 'idx_product_shop_mappings_shop_sku_product%'
                OR indexname LIKE 'idx_product_shop_mappings_product_shop%'
                OR indexname LIKE 'idx_purchase_order_sources_order_item_purchase%'
                OR indexname LIKE 'idx_purchase_orders_%'
                OR indexname LIKE 'idx_purchase_order_items_%'
                OR indexname LIKE 'idx_purchase_order_sources_purchase_item_order%'
                OR indexname LIKE 'idx_scheduled_task_%'
            )
            ORDER BY pg_relation_size(indexname::regclass) DESC
        """))

        rows = result.fetchall()
        if rows:
            print(f"\n{'索引名称':<50} {'表':<18} {'大小':<15}")
            print("-" * 86)
            for row in rows:
                print(f"{row[0]:<50} {row[1]:<18} {row[2]:<15}")
        else:
            print("未找到自定义索引")


if __name__ == "__main__":
    print("=" * 60)
    print("数据库索引优化迁移")
    print("=" * 60)

    # 创建索引
    create_indexes()

    # 更新统计信息
    analyze_tables()

    # 显示统计信息
    show_index_stats()

    print("\n" + "=" * 60)
    print("迁移完成！订单列表查询性能应该会有显著提升。")
    print("=" * 60)
