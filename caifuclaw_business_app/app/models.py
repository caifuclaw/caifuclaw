# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime
import uuid

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def generate_internal_order_no() -> str:
    return uuid.uuid4().hex[:16].upper()


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = ({"comment": "角色表"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, comment="角色编码")
    name: Mapped[str] = mapped_column(String(120), comment="角色名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="说明")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否系统角色")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    menu_permissions: Mapped[list["RoleMenuPermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")
    users: Mapped[list["LocalUser"]] = relationship(back_populates="role")
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class RoleMenuPermission(Base):
    __tablename__ = "role_menu_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "menu_code", name="uq_role_menu_permission"),
        {"comment": "角色菜单权限表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True, comment="角色ID")
    menu_code: Mapped[str] = mapped_column(String(80), index=True, comment="菜单编码")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")

    role: Mapped["Role"] = relationship(back_populates="menu_permissions")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        Index("ix_user_roles_user_id", "user_id"),
        Index("ix_user_roles_role_id", "role_id"),
        {"comment": "用户角色关联表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("local_users.id", ondelete="CASCADE"), comment="用户ID")
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), comment="角色ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")

    user: Mapped["LocalUser"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")


class LocalUser(Base):
    __tablename__ = "local_users"
    __table_args__ = ({"comment": "本地登录用户表（CaifuClaw AI 前端管理后台账号）"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, comment="登录用户名（唯一）")
    password_hash: Mapped[str] = mapped_column(String(255), comment="密码哈希（bcrypt）")
    display_name: Mapped[str] = mapped_column(String(120), default="", comment="显示名称")
    wecom_mobile: Mapped[str] = mapped_column(String(20), default="", comment="企微手机号")
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True, comment="角色ID")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    role: Mapped["Role | None"] = relationship(back_populates="users")
    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    table_preferences: Mapped[list["UserTablePreference"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserTablePreference(Base):
    __tablename__ = "user_table_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "table_key", name="uq_user_table_preferences_user_table"),
        Index("ix_user_table_preferences_user_id", "user_id"),
        Index("ix_user_table_preferences_table_key", "table_key"),
        {"comment": "用户表格个性化配置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("local_users.id", ondelete="CASCADE"), comment="用户ID")
    table_key: Mapped[str] = mapped_column(String(160), comment="表格唯一标识")
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="用户表格配置JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    user: Mapped["LocalUser"] = relationship(back_populates="table_preferences")


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "account_id", name="uq_local_platform_account"),
        {"comment": "平台店铺账号表（每个电商平台的卖家账号及其加密凭据）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码（ozon/allegro/wildberries/joom_logistics/mercadolibre）")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识（如 Ozon Client-Id）")
    display_name: Mapped[str] = mapped_column(String(160), default="", comment="店铺展示名（如 OZON DEMO SHOP A）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用（false 时跳过定时同步）")

    credential_type: Mapped[str] = mapped_column(String(40), default="api_key", comment="凭据类型（api_key/oauth/session 等）")
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, comment="Fernet 加密后的凭据字节（含 client_id/api_key 等明文 JSON）")

    status: Mapped[str] = mapped_column(String(40), default="active", comment="账号状态（active/disabled）")
    authorization_status: Mapped[str] = mapped_column(String(40), default="unauthorized", comment="授权状态（authorized/unauthorized/expired）")
    token_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="Token 是否有效（OAuth 类平台使用）")
    token_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Token 相关提示信息")
    last_authorized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近一次授权完成时间")
    authorization_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="授权过期时间")
    session_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="会话过期时间")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近一次订单同步时间")
    last_sync_status: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="最近一次同步状态（success/failed: xxx）")
    credentials_version: Mapped[str] = mapped_column(String(80), default="", comment="凭据版本标识（用于迁移/轮转追踪）")

    auth_type: Mapped[str] = mapped_column(String(40), default="api_key", comment="鉴权类型（与 credential_type 对应）")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, comment="平台扩展配置（JSONB：base_url/accepted_statuses/cutoff 窗口等）")
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="创建者用户名")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class OAuthAuthorizationSession(Base):
    __tablename__ = "oauth_authorization_sessions"
    __table_args__ = (
        UniqueConstraint("state", name="uq_oauth_authorization_sessions_state"),
        Index("ix_oauth_authorization_sessions_account", "platform", "account_id"),
        Index("ix_oauth_authorization_sessions_status", "status"),
        {"comment": "店铺首次 OAuth 授权会话"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform_account_id: Mapped[int] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="CASCADE"),
        index=True,
        comment="店铺账号ID",
    )
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    state: Mapped[str] = mapped_column(String(160), unique=True, index=True, comment="OAuth state")
    client_id: Mapped[str] = mapped_column(String(255), default="", comment="OAuth Client ID")
    redirect_uri: Mapped[str] = mapped_column(Text, default="", comment="OAuth 回调地址")
    authorize_url: Mapped[str] = mapped_column(Text, default="", comment="OAuth 授权地址")
    token_url: Mapped[str] = mapped_column(Text, default="", comment="OAuth Token 地址")
    refresh_url: Mapped[str] = mapped_column(Text, default="", comment="OAuth Token 刷新地址")
    scopes: Mapped[list] = mapped_column(JSONB, default=list, comment="OAuth scopes")
    status: Mapped[str] = mapped_column(String(40), default="pending", comment="pending/success/failed/expired")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="授权错误信息")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="会话过期时间")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class TrafficMetric(Base):
    __tablename__ = "traffic_metrics"
    __table_args__ = (
        UniqueConstraint("record_key", name="uq_traffic_metrics_record_key"),
        Index("ix_traffic_metrics_account_period", "platform_account_id", "period_start", "period_end"),
        Index("ix_traffic_metrics_grain_stat_date", "grain", "stat_date"),
        Index(
            "ix_traffic_metrics_account_grain_stat_date",
            "platform_account_id",
            "grain",
            "stat_date",
        ),
        Index(
            "ix_traffic_metrics_grain_period_account",
            "grain",
            "period_start",
            "period_end",
            "platform_account_id",
        ),
        Index("ix_traffic_metrics_dimensions", "platform", "account_id", "source", "grain", "region"),
        Index("ix_traffic_metrics_sku", "sku"),
        {"comment": "跨平台流量分析明细（按平台原始统计口径保存）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    record_key: Mapped[str] = mapped_column(String(64), comment="标准维度幂等键")
    platform_account_id: Mapped[int] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="CASCADE"), index=True, comment="平台店铺ID"
    )
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    shop_name: Mapped[str] = mapped_column(String(160), default="", comment="店铺名称快照")
    source: Mapped[str] = mapped_column(String(20), default="organic", comment="流量来源 organic/ads")
    grain: Mapped[str] = mapped_column(String(30), default="daily", comment="统计口径 daily/date_range/rolling_30d")
    stat_date: Mapped[date] = mapped_column(Date, index=True, comment="统计日期或快照日期")
    period_start: Mapped[date] = mapped_column(Date, index=True, comment="统计周期开始")
    period_end: Mapped[date] = mapped_column(Date, index=True, comment="统计周期结束")
    region: Mapped[str] = mapped_column(String(40), default="", comment="站点或地区")
    entity_type: Mapped[str] = mapped_column(String(30), default="sku", comment="实体类型 sku/shop/campaign")
    entity_id: Mapped[str] = mapped_column(String(180), default="", comment="平台商品或实体ID")
    sku: Mapped[str] = mapped_column(String(255), default="", comment="店铺SKU")
    product_name: Mapped[str] = mapped_column(String(500), default="", comment="商品名称")
    impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="曝光量")
    clicks: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="点击或访问量")
    add_to_cart: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="加购量")
    orders: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="订单数")
    buyers: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="买家数")
    units_sold: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="售出件数")
    negative_reviews: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="负面评价数")
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True, comment="成交金额")
    currency: Mapped[str] = mapped_column(String(16), default="", comment="币种")
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, comment="原始口径补充信息")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, comment="同步时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class TrafficSyncRun(Base):
    __tablename__ = "traffic_sync_runs"
    __table_args__ = (
        Index("ix_traffic_sync_runs_account_started", "platform_account_id", "started_at"),
        Index("ix_traffic_sync_runs_account_latest", "platform_account_id", "id"),
        Index("ix_traffic_sync_runs_status", "status"),
        {"comment": "流量分析平台采集运行记录"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform_account_id: Mapped[int] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="CASCADE"), index=True, comment="平台店铺ID"
    )
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    shop_name: Mapped[str] = mapped_column(String(160), default="", comment="店铺名称快照")
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        comment="pending/running/success/partial_success/failed/timed_out",
    )
    date_from: Mapped[date] = mapped_column(Date, comment="当前分析周期开始")
    date_to: Mapped[date] = mapped_column(Date, comment="当前分析周期结束")
    rows_written: Mapped[int] = mapped_column(Integer, default=0, comment="写入明细数量")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="错误信息")
    triggered_by: Mapped[str] = mapped_column(String(80), default="", comment="触发用户")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")


class LogisticsAuthorization(Base):
    __tablename__ = "logistics_authorizations"
    __table_args__ = (
        UniqueConstraint("carrier_code", "account_name", name="uq_logistics_authorizations_carrier_account"),
        Index("ix_logistics_authorizations_carrier_code", "carrier_code"),
        Index("ix_logistics_authorizations_enabled", "enabled"),
        {"comment": "物流公司授权配置表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    carrier_code: Mapped[str] = mapped_column(String(80), comment="物流公司编码")
    carrier_name: Mapped[str] = mapped_column(String(160), default="", comment="物流公司名称")
    account_name: Mapped[str] = mapped_column(String(160), default="", comment="授权账号名称")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    authorization_status: Mapped[str] = mapped_column(String(40), default="unauthorized", comment="授权状态")
    token_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="授权信息是否有效")
    token_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="授权校验提示")
    credential_type: Mapped[str] = mapped_column(String(40), default="api_key", comment="凭据类型")
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, comment="加密后的物流授权 JSON")
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="物流公司差异化配置 JSON")
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="非敏感扩展设置 JSON")
    last_authorized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近授权时间")
    authorization_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="授权到期时间")
    credentials_version: Mapped[str] = mapped_column(String(80), default="", comment="凭据版本")
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="创建者用户名")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class LogisticsOrderSubmission(Base):
    __tablename__ = "logistics_order_submissions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "carrier_code",
            "customer_order_no",
            name="uq_logistics_order_submissions_customer_order",
        ),
        Index("ix_logistics_order_submissions_status", "status"),
        Index("ix_logistics_order_submissions_transaction", "platform", "account_id", "transaction_id"),
        {"comment": "第三方物流订单提交幂等记录，不保存收件人隐私"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    tenant_id: Mapped[str] = mapped_column(String(80), index=True, comment="租户ID")
    carrier_code: Mapped[str] = mapped_column(String(80), index=True, comment="物流公司编码")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="来源平台")
    account_id: Mapped[str] = mapped_column(String(120), default="", index=True, comment="来源店铺账号")
    transaction_id: Mapped[str] = mapped_column(String(160), default="", index=True, comment="平台交易ID")
    customer_order_no: Mapped[str] = mapped_column(String(160), comment="提交给物流商的客户订单号")
    local_order_ids: Mapped[list] = mapped_column(JSONB, default=list, comment="关联本地订单ID")
    request_hash: Mapped[str] = mapped_column(String(64), default="", comment="不含签名与隐私的请求指纹")
    provider_order_no: Mapped[str] = mapped_column(String(160), default="", index=True, comment="物流商订单号")
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="下单渠道ID")
    status: Mapped[str] = mapped_column(String(40), default="pending", comment="pending/succeeded/failed/uncertain")
    attempts: Mapped[int] = mapped_column(Integer, default=0, comment="提交次数")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="最近一次错误")
    response_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="物流商响应，不含请求隐私")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="成功提交时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class LogisticsMatchRule(Base):
    __tablename__ = "logistics_match_rules"
    __table_args__ = (
        Index("ix_logistics_match_rules_enabled_priority", "enabled", "priority"),
        Index("ix_logistics_match_rules_platform_priority", "platform", "enabled", "priority"),
        {"comment": "物流规则表：按平台、店铺和目的国家给订单匹配物流渠道"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    name: Mapped[str] = mapped_column(String(160), index=True, comment="规则名称")
    platform: Mapped[str] = mapped_column(String(40), default="", index=True, comment="适用平台代码")
    priority: Mapped[int] = mapped_column(Integer, default=10, index=True, comment="优先级，数值越小越优先")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, comment="是否启用")
    shop_names: Mapped[list] = mapped_column(JSONB, default=list, comment="来源店铺列表，匹配 shop_id/shop_name/account_id")
    is_overseas_warehouse: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="是否海外仓订单；为空时不限制")
    country_codes: Mapped[list] = mapped_column(JSONB, default=list, comment="目的国家 ISO-2 代码列表")
    logistics_channel: Mapped[str] = mapped_column(String(160), default="", comment="命中后显示的物流渠道")
    carrier_code: Mapped[str] = mapped_column(String(80), default="", comment="命中物流授权的物流商编码")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="创建者用户名")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    __table_args__ = (
        UniqueConstraint("platform", name="uq_platform_settings_platform"),
        Index("ix_platform_settings_enabled", "enabled"),
        {"comment": "平台总开关设置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    platform_name: Mapped[str] = mapped_column(String(160), default="", comment="平台名称")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="显示顺序")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class SyncSetting(Base):
    __tablename__ = "sync_settings"
    __table_args__ = (
        UniqueConstraint("platform", "account_id", name="uq_sync_setting_account"),
        {"comment": "同步策略表（按店铺粒度控制定时任务开关与频率）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用定时同步")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=1200, comment="定时同步间隔（秒）")
    dry_run_fulfillment: Mapped[bool] = mapped_column(Boolean, default=True, comment="发货操作是否 dry-run（true 时只记录不调用平台发货接口）")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近一次任务运行时间")


class SchedulerHeartbeat(Base):
    __tablename__ = "scheduler_heartbeats"
    __table_args__ = (
        UniqueConstraint("owner_id", name="uq_scheduler_heartbeats_owner"),
        Index("ix_scheduler_heartbeats_last_seen", "last_seen_at"),
        {"comment": "调度器进程心跳表（用于确认唯一调度 owner）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    owner_id: Mapped[str] = mapped_column(String(160), comment="调度器 owner 标识")
    host: Mapped[str] = mapped_column(String(160), default="", comment="主机名")
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="进程ID")
    is_leader: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否当前 leader")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="启动时间")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="最近心跳时间")
    message: Mapped[str] = mapped_column(Text, default="", comment="状态说明")


class SyncAccountState(Base):
    __tablename__ = "sync_account_states"
    __table_args__ = (
        UniqueConstraint("platform", "account_id", "job_type", name="uq_sync_account_state"),
        Index("ix_sync_account_states_next_due", "next_due_at"),
        Index("ix_sync_account_states_last_success", "last_success_at"),
        Index("ix_sync_account_states_status", "last_status"),
        {"comment": "店铺同步运行状态表（心跳、超时、补偿状态）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    job_type: Mapped[str] = mapped_column(String(80), default="sync_orders", comment="任务类型")
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近开始时间")
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近结束时间")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近成功时间")
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近失败时间")
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="下次应执行时间")
    last_status: Mapped[str] = mapped_column(String(40), default="", comment="最近状态")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, comment="连续失败次数")
    overdue_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始超时时间")
    catchup_required: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否需要补偿同步")
    catchup_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="补偿开始时间")
    catchup_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="补偿结束时间")
    last_message: Mapped[str] = mapped_column(Text, default="", comment="最近消息")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class SyncAuditLog(Base):
    __tablename__ = "sync_audit_logs"
    __table_args__ = (
        Index("ix_sync_audit_logs_created", "created_at"),
        Index("ix_sync_audit_logs_event_type", "event_type"),
        Index("ix_sync_audit_logs_account", "platform", "account_id"),
        {"comment": "同步调度审计日志表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    event_type: Mapped[str] = mapped_column(String(80), comment="事件类型")
    platform: Mapped[str] = mapped_column(String(40), default="", index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), default="", index=True, comment="平台账号标识")
    job_type: Mapped[str] = mapped_column(String(80), default="", comment="任务类型")
    status: Mapped[str] = mapped_column(String(40), default="", comment="状态")
    message: Mapped[str] = mapped_column(Text, default="", comment="事件说明")
    owner_id: Mapped[str] = mapped_column(String(160), default="", comment="调度器 owner")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, comment="扩展信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")


class PlatformPrintSetting(Base):
    __tablename__ = "platform_print_settings"
    __table_args__ = (
        UniqueConstraint("platform", "document_type", name="uq_platform_print_settings_platform_document"),
        {"comment": "平台打印设置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    document_type: Mapped[str] = mapped_column(String(40), default="label", comment="单据类型")
    printer_name: Mapped[str] = mapped_column(String(255), default="", comment="打印机名称")
    printer_system: Mapped[str] = mapped_column(String(40), default="", comment="打印机系统")
    printer_device_uri: Mapped[str] = mapped_column(String(500), default="", comment="打印机设备URI")
    printer_driver_name: Mapped[str] = mapped_column(String(255), default="", comment="打印机驱动名称")
    printer_port_name: Mapped[str] = mapped_column(String(255), default="", comment="打印机端口名称")
    printer_fingerprint: Mapped[str] = mapped_column(String(80), default="", comment="打印机指纹")
    page_orientation: Mapped[str] = mapped_column(String(20), default="auto", comment="打印方向(auto/portrait/landscape)")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class ShippingDeadlineSetting(Base):
    __tablename__ = "shipping_deadline_settings"
    __table_args__ = (
        UniqueConstraint("platform", name="uq_shipping_deadline_settings_platform"),
        {"comment": "发出截止时间计算规则"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码，other 表示其他未枚举平台")
    base_date_field: Mapped[str] = mapped_column(String(40), default="platform_created_at", comment="基准日期字段")
    offset_days: Mapped[int] = mapped_column(Integer, default=0, comment="偏移天数，可为负数")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="显示顺序")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class DashboardPlatformSetting(Base):
    __tablename__ = "dashboard_platform_settings"
    __table_args__ = (
        UniqueConstraint("platform", name="uq_dashboard_platform_settings_platform"),
        {"comment": "工作台平台经营参数"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), unique=True, index=True, comment="平台代码，other 表示默认规则")
    receipt_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("1"), comment="预计收款比例")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class EmailSmtpSetting(Base):
    __tablename__ = "email_smtp_settings"
    __table_args__ = ({"comment": "邮件 SMTP 发件配置"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    provider: Mapped[str] = mapped_column(String(40), default="qq", comment="邮箱服务商")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用")
    smtp_host: Mapped[str] = mapped_column(String(255), default="smtp.qq.com", comment="SMTP 主机")
    smtp_port: Mapped[int] = mapped_column(Integer, default=465, comment="SMTP 端口")
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否使用 SSL")
    sender_email: Mapped[str] = mapped_column(String(255), default="", comment="发件邮箱")
    sender_name: Mapped[str] = mapped_column(String(120), default="", comment="发件人名称")
    encrypted_auth_code: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, comment="加密后的 SMTP 授权码")
    notification_recipients: Mapped[dict] = mapped_column(JSONB, default=dict, comment="按异常类型配置的邮件收件人")
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近测试时间")
    last_test_status: Mapped[str] = mapped_column(String(40), default="", comment="最近测试状态")
    last_test_message: Mapped[str] = mapped_column(Text, default="", comment="最近测试消息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class WeComRobotSetting(Base):
    __tablename__ = "wecom_robot_settings"
    __table_args__ = ({"comment": "企业微信群机器人配置"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    encrypted_webhook_url: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, comment="加密后的 webhook URL")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, comment="请求超时时间（秒）")
    max_retries: Mapped[int] = mapped_column(Integer, default=2, comment="失败重试次数")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=20, comment="每分钟发送上限")
    default_mentioned_user_ids: Mapped[str] = mapped_column(Text, default="[]", comment="默认提醒用户ID列表 JSON")
    default_mentioned_list: Mapped[str] = mapped_column(Text, default="[]", comment="默认提醒成员列表 JSON")
    default_mentioned_mobile_list: Mapped[str] = mapped_column(Text, default="[]", comment="默认提醒手机号列表 JSON")
    default_prompt: Mapped[str] = mapped_column(Text, default="你有新的任务，请处理", comment="默认提示语")
    purchase_order_notify_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="采购单生成后是否发送群通知")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class TranslationProviderSetting(Base):
    __tablename__ = "translation_provider_settings"
    __table_args__ = (
        UniqueConstraint("provider", name="uq_translation_provider_settings_provider"),
        Index("ix_translation_provider_settings_enabled", "enabled"),
        {"comment": "翻译服务配置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    provider: Mapped[str] = mapped_column(String(40), default="baidu", comment="翻译服务商")
    provider_name: Mapped[str] = mapped_column(String(80), default="百度翻译", comment="翻译服务商名称")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用")
    app_id: Mapped[str] = mapped_column(String(160), default="", comment="服务商应用ID")
    encrypted_secret_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, comment="加密后的服务商密钥")
    endpoint: Mapped[str] = mapped_column(Text, default="", comment="翻译接口地址")
    source_language: Mapped[str] = mapped_column(String(20), default="auto", comment="默认源语言")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, comment="请求超时时间（秒）")
    max_retries: Mapped[int] = mapped_column(Integer, default=2, comment="失败重试次数")
    batch_size: Mapped[int] = mapped_column(Integer, default=80, comment="单批文本数量")
    batch_chars: Mapped[int] = mapped_column(Integer, default=5000, comment="单批字符数")
    provider_options_json: Mapped[str] = mapped_column(Text, default="{}", comment="服务商扩展配置 JSON")
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近测试时间")
    last_test_status: Mapped[str] = mapped_column(String(40), default="", comment="最近测试状态")
    last_test_message: Mapped[str] = mapped_column(Text, default="", comment="最近测试消息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class ModelEndpoint(Base):
    __tablename__ = "model_endpoints"
    __table_args__ = (
        UniqueConstraint("name", name="uq_model_endpoints_name"),
        Index("ix_model_endpoints_enabled", "enabled"),
        {"comment": "大模型接口配置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    name: Mapped[str] = mapped_column(String(160), index=True, comment="接口配置名称")
    base_url: Mapped[str] = mapped_column(Text, default="", comment="OpenAI-compatible 基础地址")
    encrypted_api_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, comment="加密后的 API Key")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    model_settings: Mapped[list["ModelSetting"]] = relationship(back_populates="endpoint")


class ModelSetting(Base):
    __tablename__ = "model_settings"
    __table_args__ = (
        UniqueConstraint("name", name="uq_model_settings_name"),
        Index("ix_model_settings_enabled", "enabled"),
        Index("ix_model_settings_is_default", "is_default"),
        {"comment": "大模型配置"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    name: Mapped[str] = mapped_column(String(160), index=True, comment="模型名称")
    model: Mapped[str] = mapped_column(String(160), comment="模型标识")
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("model_endpoints.id"), index=True, comment="接口配置ID")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认模型")
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否支持图片理解")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    endpoint: Mapped["ModelEndpoint"] = relationship(back_populates="model_settings")


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", "currency_code", name="uq_exchange_rates_date_currency"),
        Index("ix_exchange_rates_rate_date", "rate_date"),
        Index("ix_exchange_rates_currency_code", "currency_code"),
        Index("ix_exchange_rates_updated_at", "updated_at"),
        {"comment": "本地汇率表（从外部汇率供应商同步）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    rate_date: Mapped[date] = mapped_column(Date, comment="汇率日期")
    currency_code: Mapped[str] = mapped_column(String(12), comment="货币代码")
    currency_name: Mapped[str] = mapped_column(String(80), default="", comment="货币名称")
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), comment="汇率（1 外币 = N CNY）")
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="汇率供应商更新时间")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="本地同步时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class ExchangeRateCurrencySetting(Base):
    __tablename__ = "exchange_rate_currency_settings"
    __table_args__ = (
        UniqueConstraint("currency_code", name="uq_exchange_rate_currency_settings_code"),
        Index("ix_exchange_rate_currency_settings_enabled", "enabled"),
        {"comment": "汇率同步币别设置；无启用记录时同步全部币别"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    currency_code: Mapped[str] = mapped_column(String(12), comment="货币代码")
    currency_name: Mapped[str] = mapped_column(String(80), default="", comment="货币名称")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用同步")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("ix_scheduled_tasks_enabled", "enabled"),
        Index("ix_scheduled_tasks_task_type", "task_type"),
        {"comment": "系统定时任务"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    name: Mapped[str] = mapped_column(String(120), comment="任务名称")
    task_type: Mapped[str] = mapped_column(String(80), default="auto_order_pipeline", comment="任务类型")
    cron_expr: Mapped[str] = mapped_column(String(120), comment="Cron 表达式")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, comment="任务参数")
    remark: Mapped[str] = mapped_column(Text, default="", comment="备注")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近执行时间")
    last_status: Mapped[str] = mapped_column(String(40), default="", comment="最近执行状态")
    last_message: Mapped[str] = mapped_column(Text, default="", comment="最近执行消息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("shop_id", "platform_order_id", "posting_number", name="uq_order_shop_posting"),
        {"comment": "订单表（按 posting 粒度存储；同一 order_id 可拆多个 posting 存多行）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    internal_order_no: Mapped[str] = mapped_column(String(32), default=generate_internal_order_no, comment="内部单号")
    tenant_id: Mapped[str] = mapped_column(String(80), index=True, comment="租户ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码（ozon/allegro/...）")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    shop_id: Mapped[str] = mapped_column(String(120), index=True, comment="店铺ID（与平台账号绑定，非空，唯一键组成部分）")
    shop_name: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="店铺名称")
    site: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="站点（平台多站点时使用）")
    platform_order_id: Mapped[str] = mapped_column(String(160), index=True, comment="平台订单ID（Ozon=order_id 数字字符串，父订单标识）")
    platform_order_no: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True, comment="平台订单编号（Ozon=order_number，如 0000000001-0001）")
    posting_number: Mapped[str] = mapped_column(String(160), default="", index=True, comment="平台发货包裹号（Ozon=posting_number，如 0000000001-0001-1；同订单拆多个包裹时不同）")
    buyer_id: Mapped[str | None] = mapped_column(String(120), nullable=True, comment="买家ID")
    buyer_name: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="买家姓名")
    platform_status: Mapped[str] = mapped_column(String(80), default="", comment="平台原始状态（awaiting_packaging/awaiting_deliver/...）")
    biz_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True, comment="业务状态（待处理/配货中/已发货/已作废 等；前端状态页签依据）")
    local_status: Mapped[str] = mapped_column(String(80), default="new", index=True, comment="本地流转状态（new/shipment_creating/label_downloading/label_saved/failed_retryable）")
    fulfillment_type: Mapped[str] = mapped_column(String(40), default="FBS", index=True, comment="履约类型（FBS/FBO/FBP/FBJ/OVERSEAS_WAREHOUSE 等）")
    is_overseas_warehouse: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="是否海外仓/平台仓履约订单")
    bsi_order_no: Mapped[str] = mapped_column(String(160), default="", index=True, comment="BSI 返回的物流草稿单号")
    bsi_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="BSI 草稿成功提交时间")
    platform_handover_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="平台要求交付时间（shipment_date/ship_by_date）")
    platform_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="平台订单创建时间")
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="国家代码（ISO-2，如 RU/CN/US）")
    country_name_cn: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="国家中文名（如 俄罗斯）")
    buyer_selected_logistics: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="买家选择的物流方式")
    order_amount: Mapped[str | None] = mapped_column(String(40), nullable=True, comment="订单金额原币")
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="币种代码（CNY/RUB/USD 等）")
    payment_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="付款/下单时间")
    shipping_deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="发货截止时间（Ozon cutoff）")
    dispatch_deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="发出截止时间（按系统设置规则计算）")
    shipment_tracking_number: Mapped[str | None] = mapped_column(String(160), nullable=True, comment="运单号/跟踪号")
    logistics_channel: Mapped[str] = mapped_column(String(160), default="", comment="物流规则匹配出的物流渠道")
    logistics_carrier_code: Mapped[str] = mapped_column(String(80), default="", index=True, comment="命中物流授权的物流商编码")
    logistics_match_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="命中的物流规则ID")
    logistics_match_rule_name: Mapped[str] = mapped_column(String(160), default="", comment="命中的物流规则名称")
    logistics_match_status: Mapped[str] = mapped_column(String(40), default="unmatched", index=True, comment="物流匹配状态 matched/unmatched/manual")
    logistics_match_reason: Mapped[str] = mapped_column(Text, default="", comment="物流匹配原因")
    logistics_matched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="物流匹配时间")
    picking_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="转入配货/装配时间")
    marked_shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="标记发货时间")
    label_printed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="打印标签时间")
    handover_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="本地交付平台时间")
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="实际发货时间")
    logistics_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="最近一次物流/状态回查时间")
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict, comment="平台返回的原始 JSON（审计与字段重提取使用）")
    last_api_payload: Mapped[dict] = mapped_column(JSONB, default=dict, comment="最近一次状态回查/单条接口返回的当前订单 JSON")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="最近一次失败错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="入库时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    shipments: Mapped[list["Shipment"]] = relationship(back_populates="order")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderRiskHandling(Base):
    __tablename__ = "order_risk_handlings"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_order_risk_handling_order"),
        Index("ix_order_risk_handlings_order_id", "order_id"),
        Index("ix_order_risk_handlings_handled_at", "handled_at"),
        {"comment": "订单发货风险跟进状态"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    handled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    handled_by: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrderOperationLog(Base):
    __tablename__ = "order_operation_logs"
    __table_args__ = (
        Index("ix_order_operation_logs_order_id", "order_id"),
        Index("ix_order_operation_logs_operated_at", "operated_at"),
        Index("ix_order_operation_logs_event_key", "event_key"),
        {"comment": "订单操作日志表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), comment="关联订单ID")
    operation_type: Mapped[str] = mapped_column(String(80), default="", index=True, comment="操作类型编码")
    operation_attribute: Mapped[str] = mapped_column(String(120), default="", comment="操作属性展示名")
    description: Mapped[str] = mapped_column(Text, default="", comment="操作描述")
    operator: Mapped[str] = mapped_column(String(80), default="", comment="操作员")
    source: Mapped[str] = mapped_column(String(40), default="manual", comment="来源 manual/system/history")
    event_key: Mapped[str] = mapped_column(String(180), default="", comment="幂等事件键")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, comment="扩展上下文")
    operated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="操作时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_sku", "order_id", "sku"),
        {"comment": "订单明细表（按订单 SKU 行存储）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), comment="关联订单ID")
    sku: Mapped[str] = mapped_column(String(255), default="", index=True, comment="店铺 SKU")
    platform_product_name: Mapped[str] = mapped_column(String(500), default="", comment="平台返回的商品名称")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="商品数量")
    unit_price: Mapped[str | None] = mapped_column(String(40), nullable=True, comment="商品销售单价")
    currency: Mapped[str] = mapped_column(String(16), default="", comment="币种")
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict, comment="平台返回的商品明细原始 JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    order: Mapped[Order] = relationship(back_populates="items")


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = ({"comment": "发货记录表（一个订单可能产生多条发货流水）"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, comment="关联订单ID（orders.id）")
    platform_shipment_id: Mapped[str] = mapped_column(String(160), default="", comment="平台发货ID")
    tracking_number: Mapped[str] = mapped_column(String(160), default="", comment="运单号")
    carrier: Mapped[str] = mapped_column(String(120), default="", comment="承运商名称")
    status: Mapped[str] = mapped_column(String(80), default="created", comment="发货状态（created/label_ready/shipped/failed）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")

    order: Mapped[Order] = relationship(back_populates="shipments")
    labels: Mapped[list["LabelFile"]] = relationship(back_populates="shipment")


class OutboundScanRecord(Base):
    __tablename__ = "outbound_scan_records"
    __table_args__ = (
        Index("ix_outbound_scan_tracking", "tracking_number"),
        Index("ix_outbound_scan_order_id", "order_id"),
        Index("ix_outbound_scan_scanned_at", "scanned_at"),
        Index("ix_outbound_scan_result", "result"),
        {"comment": "outbound scan audit records"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="primary key")
    tracking_number: Mapped[str] = mapped_column(String(160), index=True, comment="tracking number from scanner")
    raw_input: Mapped[str] = mapped_column(String(255), default="", comment="raw scanner input")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True, comment="matched order id")
    platform: Mapped[str] = mapped_column(String(40), default="", comment="platform snapshot")
    shop_name: Mapped[str] = mapped_column(String(160), default="", comment="shop snapshot")
    platform_order_no: Mapped[str] = mapped_column(String(160), default="", comment="platform order number snapshot")
    posting_number: Mapped[str] = mapped_column(String(160), default="", comment="posting number snapshot")
    order_status: Mapped[str] = mapped_column(String(40), default="", comment="order status snapshot")
    platform_status: Mapped[str] = mapped_column(String(80), default="", comment="platform status snapshot")
    result: Mapped[str] = mapped_column(String(40), default="", comment="success/duplicate/not_found/invalid/error")
    message: Mapped[str] = mapped_column(Text, default="", comment="result message")
    scanned_by: Mapped[str] = mapped_column(String(80), default="", comment="operator username")
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="scan time")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="created time")


class LabelFile(Base):
    __tablename__ = "label_files"
    __table_args__ = ({"comment": "面单文件表（PDF 文件元信息；文件存储于磁盘，此处存路径和校验和）"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True, comment="关联发货记录ID（shipments.id）")
    file_path: Mapped[str] = mapped_column(Text, comment="面单文件磁盘路径")
    content_type: Mapped[str] = mapped_column(String(120), default="application/pdf", comment="文件 MIME 类型")
    sha256: Mapped[str] = mapped_column(String(64), comment="文件内容 SHA256 校验和")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")

    shipment: Mapped[Shipment] = relationship(back_populates="labels")


class SyncCursor(Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (
        UniqueConstraint("platform", "account_id", "cursor_key", name="uq_sync_cursor"),
        {"comment": "同步游标表（支持增量拉取场景，按 key 保存上一次拉取的位置/时间戳）"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    cursor_key: Mapped[str] = mapped_column(String(120), comment="游标业务键（如 last_order_time）")
    cursor_value: Mapped[str] = mapped_column(Text, default="", comment="游标值（字符串）")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


class SyncJobLog(Base):
    __tablename__ = "sync_job_logs"
    __table_args__ = ({"comment": "同步任务日志表（每次整次同步任务一条；粒度到店铺+任务类型）"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    job_type: Mapped[str] = mapped_column(String(80), default="sync_orders", comment="任务类型（sync_orders/fulfill/...）")
    status: Mapped[str] = mapped_column(String(40), default="running", comment="任务状态（running/success/failed）")
    message: Mapped[str] = mapped_column(Text, default="", comment="任务消息（成功时为统计，失败时为错误详情）")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="开始时间")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"
    __table_args__ = ({"comment": "平台 API 请求日志表（记录每次外部 HTTP 调用的请求与响应，保留 30 天）"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    platform: Mapped[str] = mapped_column(String(40), index=True, comment="平台代码")
    account_id: Mapped[str] = mapped_column(String(120), index=True, comment="平台账号标识")
    operation: Mapped[str] = mapped_column(String(80), default="", index=True, comment="操作类型")
    status: Mapped[str] = mapped_column(String(40), default="", index=True, comment="调用状态（success/failed）")
    request_id: Mapped[str] = mapped_column(String(120), default="", index=True, comment="关联请求/任务ID")
    method: Mapped[str] = mapped_column(String(10), default="POST", comment="HTTP 方法（GET/POST/...）")
    url: Mapped[str] = mapped_column(Text, comment="请求 URL（含路径）")
    request_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="请求体（JSONB；PDF 等二进制请求不记录）")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="HTTP 响应状态码")
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="响应体（JSONB；PDF 等二进制响应仅记录长度）")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="异常信息（抛出异常时记录）")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="请求耗时（毫秒）")
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, comment="扩展上下文")
    log_date: Mapped[str] = mapped_column(String(10), index=True, comment="日志日期（YYYY-MM-DD，便于按天清理）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
class ScheduledTaskRun(Base):
    __tablename__ = "scheduled_task_runs"
    __table_args__ = (
        Index("ix_scheduled_task_runs_task_id", "scheduled_task_id"),
        Index("ix_scheduled_task_runs_status", "status"),
        {"comment": "后台任务运行记录"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    scheduled_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="定时任务ID")
    task_type: Mapped[str] = mapped_column(String(80), index=True, comment="任务类型")
    trigger_mode: Mapped[str] = mapped_column(String(40), default="scheduler", comment="触发方式")
    status: Mapped[str] = mapped_column(String(40), default="running", comment="运行状态")
    summary: Mapped[str] = mapped_column(Text, default="", comment="结果摘要")
    stats_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="统计结果")
    attempt_no: Mapped[int] = mapped_column(Integer, default=0, comment="尝试次数，首次为0")
    max_retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="最大额外重试次数")
    parent_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="父运行ID")
    original_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="原始运行ID")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="下次重试时间")
    retry_reason: Mapped[str] = mapped_column(Text, default="", comment="重试原因")
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, comment="最终失败邮件是否已发送")
    email_error: Mapped[str] = mapped_column(Text, default="", comment="邮件发送错误")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="开始时间")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")


class ScheduledTaskRunStep(Base):
    __tablename__ = "scheduled_task_run_steps"
    __table_args__ = (
        Index("ix_scheduled_task_run_steps_run_id", "run_id"),
        Index("ix_scheduled_task_run_steps_step_code", "step_code"),
        {"comment": "后台任务运行步骤日志"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("scheduled_task_runs.id", ondelete="CASCADE"), index=True, comment="运行记录ID")
    step_code: Mapped[str] = mapped_column(String(80), index=True, comment="步骤编码")
    step_name: Mapped[str] = mapped_column(String(120), comment="步骤名称")
    status: Mapped[str] = mapped_column(String(40), default="running", comment="步骤状态")
    message: Mapped[str] = mapped_column(Text, default="", comment="步骤消息")
    stats_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="步骤统计")
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="步骤载荷")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="开始时间")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")


class ScheduledTaskRunOrder(Base):
    __tablename__ = "scheduled_task_run_orders"
    __table_args__ = (
        UniqueConstraint("run_id", "order_id", "platform", name="uq_scheduled_task_run_orders_run_order_platform"),
        Index("ix_scheduled_task_run_orders_run_id", "run_id"),
        Index("ix_scheduled_task_run_orders_order_id", "order_id"),
        {"comment": "后台任务订单处理明细"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    run_id: Mapped[int] = mapped_column(ForeignKey("scheduled_task_runs.id", ondelete="CASCADE"), index=True, comment="运行记录ID")
    order_id: Mapped[int] = mapped_column(Integer, index=True, comment="订单ID")
    platform: Mapped[str] = mapped_column(String(40), default="", comment="平台")
    purchase_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="采购单ID")
    pdf_generated: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否生成PDF")
    pdf_file_path: Mapped[str] = mapped_column(Text, default="", comment="PDF备份路径")
    printer_name: Mapped[str] = mapped_column(String(255), default="", comment="打印机名称")
    print_job_name: Mapped[str] = mapped_column(String(255), default="", comment="打印任务名称")
    print_submitted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否提交打印")
    print_message: Mapped[str] = mapped_column(Text, default="", comment="打印消息")
    status_before: Mapped[str] = mapped_column(String(40), default="", comment="处理前状态")
    status_after: Mapped[str] = mapped_column(String(40), default="", comment="处理后状态")
    needs_reprint: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否需要重打")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")


class OrderFollowUpExportJob(Base):
    __tablename__ = "order_follow_up_export_jobs"
    __table_args__ = (
        UniqueConstraint("scheduled_task_run_id", name="uq_order_follow_up_export_jobs_run"),
        Index("ix_order_follow_up_export_jobs_status_retry", "status", "next_retry_at", "id"),
        {"comment": "Order follow up 独立导出任务"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    scheduled_task_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_task_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="来源定时任务运行ID",
    )
    workbook_key: Mapped[str] = mapped_column(String(255), default="", index=True, comment="目标工作簿标识")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, comment="任务状态")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, comment="已执行次数")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, comment="最大执行次数")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="下次重试时间")
    claimed_by: Mapped[str] = mapped_column(String(255), default="", comment="领取任务的执行器")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="领取时间")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True, comment="执行租约截止时间")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="执行器心跳时间")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="最近一次错误")
    stats_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="导出统计")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="首次开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    items: Mapped[list["OrderFollowUpExportItem"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list["OrderFollowUpExportArtifact"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class OrderFollowUpExportItem(Base):
    __tablename__ = "order_follow_up_export_items"
    __table_args__ = (
        UniqueConstraint("job_id", "order_item_id", name="uq_order_follow_up_export_items_job_item"),
        Index("ix_order_follow_up_export_items_order_item", "order_item_id", "status", "id"),
        {"comment": "Order follow up 导出订单商品明细"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    job_id: Mapped[int] = mapped_column(
        ForeignKey("order_follow_up_export_jobs.id", ondelete="CASCADE"),
        index=True,
        comment="导出任务ID",
    )
    order_id: Mapped[int] = mapped_column(Integer, index=True, comment="订单ID快照")
    order_item_id: Mapped[int] = mapped_column(Integer, index=True, comment="订单商品ID快照")
    action: Mapped[str] = mapped_column(String(40), default="append", comment="append/update/skip")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, comment="导出状态")
    mapping_status: Mapped[str] = mapped_column(String(40), default="mapped", index=True, comment="mapped/missing")
    worksheet_row: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="订单总表行号")
    snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict, comment="导出数据快照")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="错误信息")
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="成功导出时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    job: Mapped[OrderFollowUpExportJob] = relationship(back_populates="items")


class OrderFollowUpExportArtifact(Base):
    __tablename__ = "order_follow_up_export_artifacts"
    __table_args__ = (
        UniqueConstraint("job_id", "artifact_type", name="uq_order_follow_up_export_artifacts_job_type"),
        Index("ix_order_follow_up_export_artifacts_status_id", "status", "id"),
        {"comment": "Order follow up 导出文件记录"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键ID")
    job_id: Mapped[int] = mapped_column(
        ForeignKey("order_follow_up_export_jobs.id", ondelete="CASCADE"),
        index=True,
        comment="导出任务ID",
    )
    artifact_type: Mapped[str] = mapped_column(String(40), comment="workbook/purchase_plan")
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, comment="文件状态")
    file_path: Mapped[str] = mapped_column(Text, default="", comment="文件绝对路径")
    filename: Mapped[str] = mapped_column(String(255), default="", comment="文件名")
    sha256: Mapped[str] = mapped_column(String(64), default="", comment="文件SHA-256")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, comment="文件大小")
    row_count: Mapped[int] = mapped_column(Integer, default=0, comment="本批写入行数")
    error_message: Mapped[str] = mapped_column(Text, default="", comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="创建时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")

    job: Mapped[OrderFollowUpExportJob] = relationship(back_populates="artifacts")

