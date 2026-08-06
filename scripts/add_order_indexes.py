# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""
数据库索引优化迁移脚本
为订单列表查询添加复合索引，提升查询性能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from caifuclaw_business_app.app.database import engine


def create_indexes():
    """创建优化索引"""
    indexes = [
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
    ]
    
    print("开始创建数据库索引...")
    
    with engine.connect() as conn:
        for idx, sql in enumerate(indexes, 1):
            # 提取索引名称
            for line in sql.split('\n'):
                if 'idx_order' in line:
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
        conn.execute(text("ANALYZE shipments"))
        conn.execute(text("ANALYZE label_files"))
        conn.commit()
    
    print("✓ 表统计信息更新完成")


def show_index_stats():
    """显示索引统计信息"""
    print("\n当前索引统计信息:")
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                indexname,
                pg_size_pretty(pg_relation_size(indexname::regclass)) as size
            FROM pg_indexes 
            WHERE tablename = 'orders' 
            AND indexname LIKE 'idx_order%'
            ORDER BY pg_relation_size(indexname::regclass) DESC
        """))
        
        rows = result.fetchall()
        if rows:
            print(f"\n{'索引名称':<45} {'大小':<15}")
            print("-" * 60)
            for row in rows:
                print(f"{row[0]:<45} {row[1]:<15}")
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
