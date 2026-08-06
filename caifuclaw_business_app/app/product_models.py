from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .models import LocalUser, PlatformAccount

JSON_DB = JSON().with_variant(JSONB, "postgresql")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("product_code", name="uq_products_product_code"),
        UniqueConstraint("internal_name", name="uq_products_internal_name"),
        {"comment": "产品主数据"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    internal_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    english_name: Mapped[str] = mapped_column(String(255), default="")
    cost: Mapped[object | None] = mapped_column(Numeric(12, 2), nullable=True)
    weight: Mapped[object | None] = mapped_column(Numeric(12, 3), nullable=True)
    gross_weight: Mapped[object | None] = mapped_column(Numeric(12, 3), nullable=True)
    package_length: Mapped[object | None] = mapped_column(Numeric(12, 2), nullable=True)
    package_width: Mapped[object | None] = mapped_column(Numeric(12, 2), nullable=True)
    package_height: Mapped[object | None] = mapped_column(Numeric(12, 2), nullable=True)
    ean: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    main_image_url: Mapped[str] = mapped_column(Text, default="")
    is_slow_moving_material: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    safety_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buyer_user_id: Mapped[int | None] = mapped_column(ForeignKey("local_users.id", ondelete="SET NULL"), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    mappings: Mapped[list["ProductShopMapping"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    buyer_user: Mapped[LocalUser | None] = relationship()


class ProductShopMapping(Base):
    __tablename__ = "product_shop_mappings"
    __table_args__ = (
        UniqueConstraint("shop_id", "shop_sku", name="uq_shop_sku_mapping"),
        Index("ix_product_shop_mappings_shop_sku", "shop_sku"),
        {"comment": "产品店铺SKU映射"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    shop_sku: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product: Mapped[Product] = relationship(back_populates="mappings")
    shop: Mapped[PlatformAccount] = relationship()



class ProductInventory(Base):
    __tablename__ = "product_inventory"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_product_inventory_product_id"),
        Index("ix_product_inventory_product_name", "product_name"),
        {"comment": "产品人工库存表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(255))
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    last_count_qty: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product: Mapped[Product] = relationship()


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("purchase_no", name="uq_purchase_orders_purchase_no"),
        {"comment": "采购单主表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_no: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="草稿", index=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    total_required_qty: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )
    sources: Mapped[list["PurchaseOrderSource"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )


class PurchaseOrderEditLock(Base):
    __tablename__ = "purchase_order_edit_locks"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", name="uq_purchase_order_edit_locks_order"),
        {"comment": "采购单编辑锁"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    locked_by: Mapped[str] = mapped_column(String(80), index=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    purchase_order: Mapped[PurchaseOrder] = relationship()


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        Index("ix_purchase_order_items_order_product", "purchase_order_id", "product_name"),
        {"comment": "采购单明细表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    product_name: Mapped[str] = mapped_column(String(255), index=True)
    required_qty: Mapped[int] = mapped_column(Integer, default=0)
    buyer_user_id: Mapped[int | None] = mapped_column(ForeignKey("local_users.id", ondelete="SET NULL"), nullable=True, index=True)
    buyer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    total_cost_record: Mapped[object | None] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_cost: Mapped[object | None] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_channel: Mapped[str | None] = mapped_column(String(160), nullable=True)
    purchase_qty: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()
    buyer_user: Mapped[LocalUser | None] = relationship()
    sources: Mapped[list["PurchaseOrderSource"]] = relationship(
        back_populates="purchase_order_item",
        cascade="all, delete-orphan",
    )


class PurchaseOrderSource(Base):
    __tablename__ = "purchase_order_sources"
    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_purchase_order_sources_order_item"),
        Index("ix_purchase_order_sources_purchase_order", "purchase_order_id"),
        {"comment": "采购单来源订单明细表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    purchase_order_item_id: Mapped[int] = mapped_column(ForeignKey("purchase_order_items.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    order_item_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="sources")
    purchase_order_item: Mapped[PurchaseOrderItem] = relationship(back_populates="sources")


class PurchaseOrderLog(Base):
    __tablename__ = "purchase_order_logs"
    __table_args__ = ({"comment": "采购单操作日志"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    purchase_no: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    operator: Mapped[str | None] = mapped_column(String(80), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
