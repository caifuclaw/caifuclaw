# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""重建订单相关表（orders/shipments/label_files/sync_cursors）并创建 api_request_logs；
同时对所有表和列应用中文 COMMENT（Postgres 通过 SQLAlchemy comment= 自动生成 COMMENT ON 语句）。

保留的表（不删）：local_users、platform_accounts、sync_settings、sync_job_logs。

使用方式：
    python -m scripts.rebuild_order_schema
"""
from __future__ import annotations

from sqlalchemy import text

from app.database import Base, engine
from app.models import (
    ApiRequestLog,
    LabelFile,
    LocalUser,  # noqa: F401  保证模型被 import（metadata 注册）
    Order,
    OrderOperationLog,
    PlatformAccount,  # noqa: F401
    Shipment,
    SyncCursor,
    SyncJobLog,  # noqa: F401
    SyncSetting,  # noqa: F401
)

# 需要重建的表（按外键依赖反向 drop）
TABLES_TO_REBUILD = [LabelFile.__table__, Shipment.__table__, OrderOperationLog.__table__, Order.__table__, SyncCursor.__table__]

# 需要新增/确保存在的表
TABLES_TO_ENSURE = [ApiRequestLog.__table__]

# 所有表（用于刷新 COMMENT）
ALL_TABLES = [
    LocalUser.__table__,
    PlatformAccount.__table__,
    SyncSetting.__table__,
    Order.__table__,
    OrderOperationLog.__table__,
    Shipment.__table__,
    LabelFile.__table__,
    SyncCursor.__table__,
    SyncJobLog.__table__,
    ApiRequestLog.__table__,
]


def main() -> None:
    print("==> Dropping rebuild-scope tables (cascade)...")
    with engine.begin() as conn:
        for tbl in TABLES_TO_REBUILD:
            conn.execute(text(f'DROP TABLE IF EXISTS "{tbl.name}" CASCADE'))
            print(f"   dropped: {tbl.name}")

    print("==> Creating all tables (idempotent)...")
    Base.metadata.create_all(bind=engine, tables=TABLES_TO_REBUILD + TABLES_TO_ENSURE)
    for tbl in TABLES_TO_REBUILD + TABLES_TO_ENSURE:
        print(f"   created/ensured: {tbl.name}")

    print("==> Applying table & column COMMENTs for all tables...")
    with engine.begin() as conn:
        for tbl in ALL_TABLES:
            table_comment = getattr(tbl, "comment", None)
            if table_comment:
                safe = str(table_comment).replace("'", "''")
                conn.execute(text(f"COMMENT ON TABLE \"{tbl.name}\" IS '{safe}'"))
            for col in tbl.columns:
                if col.comment:
                    safe = str(col.comment).replace("'", "''")
                    conn.execute(text(f"COMMENT ON COLUMN \"{tbl.name}\".\"{col.name}\" IS '{safe}'"))
            print(f"   commented: {tbl.name}")

    print("==> Done.")


if __name__ == "__main__":
    main()
