from datetime import date
from typing import Any, Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class MenuDto(BaseModel):
    code: str
    label: str
    path: str


class RoleDto(BaseModel):
    id: int
    code: str
    name: str
    description: str = ""
    is_system: bool = False
    enabled: bool = True
    menus: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class RoleCreateRequest(BaseModel):
    code: str
    name: str
    description: str = ""
    enabled: bool = True
    menus: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    menus: list[str] = Field(default_factory=list)


class UserDto(BaseModel):
    id: int
    username: str
    display_name: str = ""
    wecom_mobile: str = ""
    role_id: int | None = None
    role_code: str
    role_name: str = ""
    role_ids: list[int] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)
    enabled: bool
    created_at: str | None = None
    updated_at: str | None = None


class UserOptionDto(BaseModel):
    id: int
    username: str
    display_name: str = ""


class WeComMentionUserOptionDto(UserOptionDto):
    wecom_mobile: str = ""


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    wecom_mobile: str = ""
    role_id: int | None = None
    role_ids: list[int] = Field(default_factory=list)
    enabled: bool = True


class UserUpdateRequest(BaseModel):
    display_name: str = ""
    wecom_mobile: str = ""
    role_id: int | None = None
    role_ids: list[int] = Field(default_factory=list)
    enabled: bool = True


class UserResetPasswordRequest(BaseModel):
    password: str


class PlatformConfigDto(BaseModel):
    platform: str
    account_id: str
    display_name: str = ""
    enabled: bool = True
    auth_type: str = "api_key"
    credentials: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class PlatformSettingDto(BaseModel):
    id: int
    platform: str
    platform_name: str = ""
    enabled: bool = True
    updated_at: str | None = None


class PlatformSettingToggleRequest(BaseModel):
    enabled: bool


class SyncSettingDto(BaseModel):
    platform: str
    account_id: str
    enabled: bool
    interval_seconds: int
    dry_run_fulfillment: bool = False


class ManualSyncRequest(BaseModel):
    platform: str | None = None
    account_id: str | None = None
    full_refresh: bool = False


class ApiRequestLogDto(BaseModel):
    id: int
    platform: str
    account_id: str
    operation: str = ""
    status: str = ""
    request_id: str = ""
    method: str
    url: str
    request_body: dict | None = None
    response_status: int | None = None
    response_body: dict | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    extra: dict = Field(default_factory=dict)
    log_date: str
    created_at: str


class ApiRequestLogListResponse(BaseModel):
    items: list[ApiRequestLogDto]
    total: int
    page: int
    page_size: int


class ApiRequestLogSummaryDto(BaseModel):
    log_date: str
    last_created_at: str = ""
    platform: str
    account_id: str
    operation: str = ""
    url: str = ""
    total: int
    success_count: int = 0
    failed_count: int = 0
    avg_duration_ms: int | None = None
    max_duration_ms: int | None = None


class ApiRequestLogSummaryListResponse(BaseModel):
    items: list[ApiRequestLogSummaryDto]
    total: int
    page: int
    page_size: int


class DashboardMonthlySalesDto(BaseModel):
    month: str
    orders: int = 0
    avg_daily_orders: float = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_amount: float = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_aov: float = 0
    expected_receipt: float = 0
    pending: int = 0
    picking: int = 0
    shipped: int = 0
    delivered: int = 0
    voided: int = 0
    voided_rate: float = 0
    blank_currency_orders: int = 0


class DashboardDailySalesDto(BaseModel):
    date: str
    orders: int = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_amount: float = 0
    expected_receipt: float = 0
    pending: int = 0
    voided: int = 0


class DashboardShopSalesDto(BaseModel):
    platform: str = ""
    shop: str
    orders: int = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_amount: float = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_aov: float = 0
    expected_receipt: float = 0
    receipt_rate_pct: float = 100
    voided: int = 0
    blank_currency_orders: int = 0


class DashboardMtdComparisonDto(BaseModel):
    current_label: str = ""
    previous_label: str = ""
    current_orders: int = 0
    previous_orders: int = 0
    order_growth_pct: float = 0
    current_amount: float = 0
    previous_amount: float = 0
    amount_growth_pct: float = 0
    current_receipt: float = 0
    previous_receipt: float = 0
    receipt_growth_pct: float = 0
    current_pending: int = 0
    current_voided: int = 0
    previous_pending: int = 0
    previous_voided: int = 0


class DashboardRiskBucketDto(BaseModel):
    key: str
    label: str
    orders: int = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_amount: float = 0
    earliest_deadline: str | None = None
    latest_deadline: str | None = None


class DashboardRiskShopDto(BaseModel):
    platform: str
    shop: str
    pending_orders: int = 0
    pending_units: int = 0
    overdue_orders: int = 0
    due_24h: int = 0
    due_48h: int = 0
    due_later: int = 0
    # Converted to CNY; field name is kept for frontend compatibility.
    raw_amount: float = 0
    min_hours_to_deadline: float | None = None
    earliest_deadline: str | None = None


class DashboardRiskSkuDto(BaseModel):
    sku: str
    product_name: str = ""
    pending_orders: int = 0
    pending_units: int = 0
    shops: int = 0
    overdue_orders: int = 0
    earliest_deadline: str | None = None


class DashboardHotSkuDto(BaseModel):
    sku: str
    product_name: str = ""
    units_all: int = 0
    orders_all: int = 0
    units_7d: int = 0
    units_prev_7d: int = 0
    units_7d_delta: int = 0
    shops: int = 0
    platforms: str = ""
    pending_orders: int = 0


class DashboardAnalyticsResponse(BaseModel):
    generated_at: str
    total_orders: int = 0
    first_order_date: str | None = None
    last_order_date: str | None = None
    blank_currency_orders: int = 0
    monthly_sales: list[DashboardMonthlySalesDto] = Field(default_factory=list)
    daily_sales: list[DashboardDailySalesDto] = Field(default_factory=list)
    comparison_daily_sales: list[DashboardDailySalesDto] = Field(default_factory=list)
    shop_sales: list[DashboardShopSalesDto] = Field(default_factory=list)
    current_label: str = ""
    comparison_label: str = ""
    mtd_comparison: DashboardMtdComparisonDto
    risk_buckets: list[DashboardRiskBucketDto] = Field(default_factory=list)
    risk_shops: list[DashboardRiskShopDto] = Field(default_factory=list)
    risk_skus: list[DashboardRiskSkuDto] = Field(default_factory=list)
    hot_skus: list[DashboardHotSkuDto] = Field(default_factory=list)


class DashboardOverviewResponse(BaseModel):
    generated_at: str
    total_orders: int = 0
    first_order_date: str | None = None
    last_order_date: str | None = None
    blank_currency_orders: int = 0
    mtd_comparison: DashboardMtdComparisonDto


class DashboardSalesResponse(BaseModel):
    monthly_sales: list[DashboardMonthlySalesDto] = Field(default_factory=list)
    daily_sales: list[DashboardDailySalesDto] = Field(default_factory=list)
    comparison_daily_sales: list[DashboardDailySalesDto] = Field(default_factory=list)
    shop_sales: list[DashboardShopSalesDto] = Field(default_factory=list)
    current_label: str = ""
    comparison_label: str = ""


class DashboardRiskResponse(BaseModel):
    risk_buckets: list[DashboardRiskBucketDto] = Field(default_factory=list)
    risk_shops: list[DashboardRiskShopDto] = Field(default_factory=list)


class DashboardSkuResponse(BaseModel):
    risk_skus: list[DashboardRiskSkuDto] = Field(default_factory=list)
    hot_skus: list[DashboardHotSkuDto] = Field(default_factory=list)
    current_label: str = ""
    previous_label: str = ""


class OperationsDailyOrderPointDto(BaseModel):
    date: str
    orders: int = 0
    revenue_cny: float = 0


class OperationsDailyShopDto(BaseModel):
    platform: str
    account_id: str = ""
    shop: str
    days: list[OperationsDailyOrderPointDto] = Field(default_factory=list)
    total_orders: int = 0
    total_revenue_cny: float = 0


class OperationsFulfillmentRiskDto(BaseModel):
    platform: str
    overdue_orders: int = 0
    due_soon_orders: int = 0


class OperationsCustomerComplaintDto(BaseModel):
    platform: str
    shop: str
    count: int = 0
    latest_issue_at: str | None = None


class OperationsDailyReportResponse(BaseModel):
    generated_at: str
    date_from: str
    date_to: str
    shop_daily_orders: list[OperationsDailyShopDto] = Field(default_factory=list)
    fulfillment_risk: list[OperationsFulfillmentRiskDto] = Field(default_factory=list)
    customer_complaints: list[OperationsCustomerComplaintDto] = Field(default_factory=list)
    customer_complaints_data_status: Literal["pending_source", "negative_reviews"] = "pending_source"


class DashboardPlatformSettingDto(BaseModel):
    platform: str
    platform_name: str = ""
    receipt_rate_pct: float = 100
    fulfillment_days: int = 0


class DashboardSettingsResponse(BaseModel):
    items: list[DashboardPlatformSettingDto] = Field(default_factory=list)
    can_manage: bool = False


class DashboardPlatformSettingUpdateRequest(BaseModel):
    platform: str
    receipt_rate_pct: float = Field(ge=0, le=100)
    fulfillment_days: int = Field(ge=0, le=365)


class DashboardSettingsUpdateRequest(BaseModel):
    items: list[DashboardPlatformSettingUpdateRequest] = Field(default_factory=list, min_length=1)


class DashboardSettingsUpdateResponse(DashboardSettingsResponse):
    backfilled: int = 0


class ShopDto(BaseModel):
    id: int
    platform: str
    account_id: str
    shop_id: str
    display_name: str
    enabled: bool
    credential_type: str = "api_key"
    status: str = "active"
    authorization_status: str = "unauthorized"
    token_valid: bool | None = None
    token_message: str | None = None
    last_authorized_at: str | None = None
    authorization_expires_at: str | None = None
    session_expires_at: str | None = None
    last_sync_at: str | None = None
    last_sync_status: str | None = None
    credentials_version: str = ""
    created_by: str | None = None
    created_at: str | None = None
    settings: dict = Field(default_factory=dict)
    updated_at: str


class ShopCreateRequest(BaseModel):
    platform: str
    account_id: str | None = None
    shop_id: str | None = None
    display_name: str = ""
    enabled: bool = True
    credential_type: str = "api_key"
    credentials: dict
    settings: dict = Field(default_factory=dict)
    authorization_expires_at: str | None = None


class ShopUpdateRequest(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    settings: dict | None = None


class CredentialsRequest(BaseModel):
    credentials: dict
    authorization_expires_at: str | None = None


class ShopAuthorizationRequest(BaseModel):
    credentials: dict = Field(default_factory=dict)
    authorization_expires_at: str | None = None


class ShopOAuthStartRequest(BaseModel):
    credentials: dict = Field(default_factory=dict)


class ShopOAuthCompleteRequest(BaseModel):
    state: str
    code: str | None = None


class LogisticsAuthorizationDto(BaseModel):
    id: int
    carrier_code: str
    carrier_name: str
    account_name: str
    enabled: bool
    authorization_status: str = "unauthorized"
    token_valid: bool | None = None
    token_message: str | None = None
    credential_type: str = "api_key"
    credentials_masked: dict = Field(default_factory=dict)
    config_json: dict = Field(default_factory=dict)
    settings_json: dict = Field(default_factory=dict)
    last_authorized_at: str | None = None
    authorization_expires_at: str | None = None
    credentials_version: str = ""
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LogisticsAuthorizationCreateRequest(BaseModel):
    carrier_code: str
    carrier_name: str
    account_name: str = ""
    enabled: bool = True
    credential_type: str = "api_key"
    credentials: dict = Field(default_factory=dict)
    config_json: dict = Field(default_factory=dict)
    settings_json: dict = Field(default_factory=dict)
    authorization_expires_at: str | None = None


class LogisticsAuthorizationUpdateRequest(BaseModel):
    carrier_name: str | None = None
    account_name: str | None = None
    enabled: bool | None = None
    credential_type: str | None = None
    credentials: dict | None = None
    config_json: dict | None = None
    settings_json: dict | None = None
    authorization_expires_at: str | None = None


class LogisticsAuthorizationVerifyResponse(BaseModel):
    authorization_status: str
    token_valid: bool
    token_message: str
    missing_fields: list[str] = Field(default_factory=list)


class LogisticsChannelOptionDto(BaseModel):
    value: str
    label: str
    carrier_code: str
    carrier_name: str
    account_name: str = ""


class LogisticsMatchRuleDto(BaseModel):
    id: int
    name: str
    platform: str = ""
    priority: int = 10
    enabled: bool = True
    shop_names: list[str] = Field(default_factory=list)
    is_overseas_warehouse: bool | None = None
    country_codes: list[str] = Field(default_factory=list)
    logistics_channel: str = ""
    carrier_code: str = ""
    remark: str = ""
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LogisticsMatchRuleListResponse(BaseModel):
    items: list[LogisticsMatchRuleDto]
    total: int
    page: int
    page_size: int


class LogisticsMatchRulePayload(BaseModel):
    name: str
    platform: str
    priority: int = 10
    enabled: bool = True
    shop_names: list[str] = Field(default_factory=list)
    is_overseas_warehouse: bool | None = None
    country_codes: list[str] = Field(default_factory=list)
    logistics_channel: str
    remark: str = ""


class LogisticsRematchRequest(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    include_manual: bool = False
    include_shipped: bool = False


class LogisticsRematchResponse(BaseModel):
    matched: int = 0
    unmatched: int = 0
    skipped: int = 0
    total: int = 0
    message: str = ""


class OrderDto(BaseModel):
    id: int
    platform: str
    account_id: str
    shop_id: str
    shop_name: str
    site: str = ""
    platform_order_id: str
    platform_order_no: str = ""
    posting_number: str = ""
    transaction_id: str
    customer_id: str = ""
    customer_name: str = ""
    status: str
    local_status: str
    platform_status: str
    fulfillment_type: str = "FBS"
    is_overseas_warehouse: bool = False
    bsi_order_no: str = ""
    bsi_submitted_at: str | None = None
    is_joom_offline_shipping: bool = False
    logistics_label_exempt: bool = False
    platform_handover_deadline: str | None = None
    country_name_cn: str = ""
    country_code: str = ""
    buyer_selected_logistics: str = ""
    order_amount: str = ""
    currency: str = ""
    payment_at: str | None = None
    shipment_tracking_number: str = ""
    tracking_number: str = ""
    logistics_channel: str = ""
    logistics_match_rule_id: int | None = None
    logistics_match_rule_name: str = ""
    logistics_match_status: str = "unmatched"
    logistics_match_reason: str = ""
    logistics_matched_at: str | None = None
    picking_at: str | None = None
    marked_shipped_at: str | None = None
    label_printed_at: str | None = None
    handover_at: str | None = None
    shipped_at: str | None = None
    shipping_deadline_at: str | None = None
    dispatch_deadline_at: str | None = None
    remaining_shipping_seconds: int | None = None
    remaining_shipping_time: str = ""
    risk_deadline_at: str | None = None
    risk_bucket: str = ""
    risk_handled: bool = False
    risk_handled_at: str | None = None
    risk_handled_by: str = ""
    risk_handling_note: str = ""
    has_label: bool = False
    label_path: str = ""
    created_at: str
    updated_at: str


class OrderSearchSummary(BaseModel):
    submitted: int = 0
    unique: int = 0
    matched: int = 0
    unmatched_numbers: list[str] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    items: list[OrderDto]
    total: int
    page: int
    page_size: int
    search_summary: OrderSearchSummary | None = None


class OrderSearchRequest(BaseModel):
    status: str | None = None
    risk: str | None = None
    shop: str | None = None
    shop_ids: str | None = None
    platform: str | None = None
    numbers: list[str] = Field(default_factory=list)
    product_keyword: str | None = None
    payment_start: str | None = None
    payment_end: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class OrderExportRequest(OrderSearchRequest):
    order_ids: list[int] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class OrderDetailItemDto(BaseModel):
    id: int
    sku: str = ""
    platform_product_name: str = ""
    quantity: int = 1
    unit_price: str = ""
    currency: str = ""
    product_code: str = ""
    product_name: str = ""
    product_cost: float | None = None
    product_weight: float | None = None


class OrderOperationLogChangeDto(BaseModel):
    field: str = ""
    label: str = ""
    before: str = ""
    after: str = ""


class OrderOperationLogDto(BaseModel):
    id: int
    operation_type: str = ""
    operation_attribute: str = ""
    description: str = ""
    operator: str = ""
    source: str = ""
    result: str = "success"
    changes: list[OrderOperationLogChangeDto] = Field(default_factory=list)
    task_run_id: int | None = None
    sync_job_log_id: int | None = None
    operated_at: str
    created_at: str


class OrderOperationLogListResponse(BaseModel):
    items: list[OrderOperationLogDto] = Field(default_factory=list)
    has_more: bool = False
    next_before_id: int | None = None


class OrderDetailDto(OrderDto):
    internal_order_no: str = ""
    items: list[OrderDetailItemDto] = Field(default_factory=list)
    operation_logs: list[OrderOperationLogDto] = Field(default_factory=list)


class OrderSummaryDto(BaseModel):
    order_id: int
    item_id: int
    picking_at: str | None = None
    platform: str
    shop_name: str = ""
    platform_created_at: str | None = None
    order_no: str = ""
    status: str = ""
    platform_status: str = ""
    platform_order_no: str = ""
    platform_order_id: str = ""
    posting_number: str = ""
    country_code: str = ""
    country_name_cn: str = ""
    customer_name: str = ""
    sku: str = ""
    platform_product_name: str = ""
    quantity: int = 1
    unit_price: str = ""
    currency: str = ""
    buyer_selected_logistics: str = ""
    shipping_deadline_at: str | None = None
    shipment_tracking_number: str = ""
    tracking_number: str = ""
    dispatch_deadline_at: str | None = None
    product_name: str = ""
    customer_confirm: str = ""
    warning: str = ""
    shipping_time: str | None = None
    purchase_generated: bool = False
    purchase_no: str = ""


class OrderSummaryResponse(BaseModel):
    items: list[OrderSummaryDto]
    total: int
    page: int
    page_size: int
    has_more: bool = False


class OrderBatchRequest(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    allow_missing_tracking: bool = False


class OrderRiskHandlingRequest(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    handled: bool = True
    note: str = Field(default="", max_length=1000)


class OrderLogisticsChannelBatchRequest(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    logistics_channel: str = ""


class OrderBatchResponse(BaseModel):
    updated: int
    message: str
    purchase_order_id: int | None = None
    purchase_no: str | None = None


class OrderWanbangTestItemDto(BaseModel):
    order_id: int
    order_no: str = ""
    success: bool = False
    account_name: str = ""
    process_code: str = ""
    tracking_number: str = ""
    parcel_status: str = ""
    reference_id: str = ""
    label_ready: bool = False
    label_attempts: int = 0
    label_bytes: int = 0
    label_sha256: str = ""
    label_path: str = ""
    error: str = ""


class OrderWanbangTestResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    message: str
    items: list[OrderWanbangTestItemDto] = Field(default_factory=list)


class OutboundScanRequest(BaseModel):
    tracking_number: str
    raw_input: str | None = None


class OutboundScanRecordDto(BaseModel):
    id: int
    tracking_number: str
    raw_input: str = ""
    order_id: int | None = None
    platform: str = ""
    shop_name: str = ""
    platform_order_no: str = ""
    posting_number: str = ""
    order_status: str = ""
    platform_status: str = ""
    result: str
    message: str = ""
    scanned_by: str = ""
    scanned_at: str
    created_at: str


class OutboundScanResponse(BaseModel):
    result: str
    message: str
    record: OutboundScanRecordDto


class OutboundScanListResponse(BaseModel):
    items: list[OutboundScanRecordDto]
    total: int
    page: int
    page_size: int


class OutboundScanStatsResponse(BaseModel):
    success: int = 0
    duplicate: int = 0
    not_found: int = 0
    invalid: int = 0
    error: int = 0
    total: int = 0
    last_scanned_at: str | None = None


class ProductShopDto(BaseModel):
    id: int
    display_name: str
    platform: str


class ProductDto(BaseModel):
    id: int
    product_code: str
    internal_name: str
    english_name: str = ""
    cost: float | None = None
    weight: float | None = None
    gross_weight: float | None = None
    package_length: float | None = None
    package_width: float | None = None
    package_height: float | None = None
    ean: str = ""
    description: str = ""
    main_image_url: str = ""
    is_slow_moving_material: bool = False
    safety_stock: int | None = None
    buyer_user_id: int | None = None
    buyer_name: str = ""
    enabled: bool
    mappings: dict[str, list[str]] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ProductListResponse(BaseModel):
    shops: list[ProductShopDto]
    users: list[UserOptionDto] = Field(default_factory=list)
    items: list[ProductDto]
    total: int
    page: int
    page_size: int


class ProductUpsertRequest(BaseModel):
    internal_name: str
    english_name: str = ""
    cost: float | None = None
    weight: float | None = None
    gross_weight: float | None = None
    package_length: float | None = None
    package_width: float | None = None
    package_height: float | None = None
    ean: str = ""
    description: str = ""
    main_image_url: str = ""
    is_slow_moving_material: bool = False
    safety_stock: int | None = None
    buyer_user_id: int | None = None
    enabled: bool = True
    mappings: dict[str, list[str]] = Field(default_factory=dict)


class ProductBatchRequest(BaseModel):
    product_ids: list[int] = Field(default_factory=list)


class InventoryDto(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_name: str
    stock_qty: int = 0
    last_count_qty: int = 0
    safety_stock: int | None = None
    stock_status: str = ""
    remark: str = ""
    updated_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class InventoryListResponse(BaseModel):
    items: list[InventoryDto]
    total: int
    page: int
    page_size: int


class InventoryUpsertRequest(BaseModel):
    product_id: int
    stock_qty: int = 0
    last_count_qty: int = 0
    safety_stock: int | None = Field(default=None, ge=0)
    remark: str = ""


class PurchaseOrderGenerateRequest(BaseModel):
    order_item_ids: list[int] = Field(default_factory=list)
    remark: str = ""


class PurchaseOrderItemDto(BaseModel):
    id: int
    product_id: int | None = None
    product_name: str
    required_qty: int = 0
    buyer_user_id: int | None = None
    buyer: str = ""
    total_cost_record: float | None = None
    purchase_cost: float | None = None
    purchase_channel: str = ""
    purchase_qty: int = 0
    remark: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class PurchaseOrderSourceDto(BaseModel):
    id: int
    order_id: int
    order_item_id: int
    product_id: int | None = None
    product_name: str
    quantity: int = 0
    created_at: str | None = None


class PurchaseOrderDto(BaseModel):
    id: int
    purchase_no: str
    purchase_date: str | None = None
    source_count: int = 0
    item_count: int = 0
    total_required_qty: int = 0
    created_by: str | None = None
    remark: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class PurchaseOrderDetailDto(PurchaseOrderDto):
    lock_acquired: bool = False
    lock_owner: str = ""
    lock_expires_at: str | None = None
    items: list[PurchaseOrderItemDto] = Field(default_factory=list)
    sources: list[PurchaseOrderSourceDto] = Field(default_factory=list)


class PurchaseOrderListResponse(BaseModel):
    items: list[PurchaseOrderDto]
    total: int
    page: int
    page_size: int


class PurchaseOrderUpdateRequest(BaseModel):
    purchase_date: str | None = None
    remark: str = ""


class PurchaseOrderItemUpdateRequest(BaseModel):
    buyer_user_id: int | None = None
    buyer: str = ""
    total_cost_record: float | None = None
    purchase_cost: float | None = None
    purchase_channel: str = ""
    purchase_qty: int = 0
    remark: str = ""


class PurchaseOrderEditLockRequest(BaseModel):
    force: bool = False


class PurchaseOrderEditLockDto(BaseModel):
    purchase_order_id: int
    lock_acquired: bool = False
    lock_owner: str = ""
    lock_expires_at: str | None = None
    message: str = ""


class PurchaseDetailDto(BaseModel):
    purchase_order_id: int
    item_id: int
    purchase_no: str
    purchase_date: str | None = None
    picking_date: str | None = None
    product_name: str = ""
    daily_order_qty: int = 0
    stock_qty: int = 0
    pending_purchase_qty: int = 0
    buyer_user_id: int | None = None
    buyer: str = ""
    total_cost_record: float | None = None
    purchase_cost: float | None = None
    purchase_channel: str = ""
    purchase_qty: int = 0
    remark: str = ""


class PurchaseDetailListResponse(BaseModel):
    items: list[PurchaseDetailDto]
    total: int
    page: int
    page_size: int


class PlatformPrintSettingDto(BaseModel):
    id: int
    platform: str
    document_type: str = "label"
    document_type_name: str = "面单打印"
    printer_name: str = ""
    printer_system: str = ""
    printer_device_uri: str = ""
    printer_driver_name: str = ""
    printer_port_name: str = ""
    printer_fingerprint: str = ""
    page_orientation: str = "auto"
    page_orientation_name: str = "自动"
    enabled: bool = True
    remark: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class PrinterDto(BaseModel):
    name: str
    display_name: str = ""
    system: str = ""
    device_uri: str = ""
    driver_name: str = ""
    port_name: str = ""
    fingerprint: str = ""
    status: str = ""
    is_default: bool = False
    online: bool | None = None


class PrinterMonitorRequest(BaseModel):
    printer_name: str
    auto_recover: bool = True
    max_retries: int = Field(default=3, ge=1, le=10)
    scheduled_task_id: int | None = None
    recipients: str = ""


class PrinterMonitorResultDto(BaseModel):
    printer_name: str = ""
    resolved_printer_name: str = ""
    status: str = ""
    message: str = ""
    exists: bool = False
    paused: bool = False
    accepting: bool | None = None
    offline: bool = False
    job_count: int = 0
    recovered: bool = False
    recovery_attempts: int = 0
    email_sent: bool = False
    email_error: str = ""
    attempts: list[dict] = Field(default_factory=list)
    snapshots: list[dict] = Field(default_factory=list)


class PlatformPrintSettingUpsertRequest(BaseModel):
    platform: str
    document_type: str = "label"
    printer_name: str = ""
    page_orientation: str = "auto"
    enabled: bool = True
    remark: str = ""


class ShippingDeadlineSettingDto(BaseModel):
    id: int
    platform: str
    platform_name: str = ""
    base_date_field: str = "platform_created_at"
    base_date_field_name: str = "创建时间"
    offset_days: int = 0
    sort_order: int = 0
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class ShippingDeadlineSettingUpsertRequest(BaseModel):
    platform: str
    base_date_field: str = "platform_created_at"
    offset_days: int = 0
    sort_order: int = 0
    enabled: bool = True


class ShippingDeadlineSettingsUpdateRequest(BaseModel):
    items: list[ShippingDeadlineSettingUpsertRequest] = Field(default_factory=list)


class ShippingDeadlineSettingsUpdateResponse(BaseModel):
    items: list[ShippingDeadlineSettingDto]
    backfilled: int = 0


class EmailProviderDto(BaseModel):
    code: str
    name: str
    smtp_host: str
    smtp_port: int
    use_ssl: bool = True
    auth_code_hint: str = ""
    sender_hint: str = ""


class EmailNotificationRecipientsDto(BaseModel):
    wanbang_tracking_failure: str = ""
    bsi_address_anomaly: str = ""


class EmailSmtpSettingDto(BaseModel):
    provider: str = "qq"
    enabled: bool = False
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    use_ssl: bool = True
    sender_email: str = ""
    sender_name: str = ""
    notification_recipients: EmailNotificationRecipientsDto = Field(default_factory=EmailNotificationRecipientsDto)
    has_auth_code: bool = False
    last_test_at: str | None = None
    last_test_status: str = ""
    last_test_message: str = ""
    updated_at: str | None = None


class EmailSmtpSettingUpdateRequest(BaseModel):
    provider: str = "qq"
    enabled: bool = False
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    use_ssl: bool = True
    sender_email: str = ""
    sender_name: str = ""
    notification_recipients: EmailNotificationRecipientsDto = Field(default_factory=EmailNotificationRecipientsDto)
    auth_code: str | None = None


class EmailTestRequest(BaseModel):
    recipient: str


class WeComRobotSettingDto(BaseModel):
    has_webhook_url: bool = False
    webhook_url_masked: str = ""
    timeout_seconds: int = 30
    max_retries: int = 2
    rate_limit_per_minute: int = 20
    default_mentioned_user_ids: list[int] = Field(default_factory=list)
    default_mentioned_list: list[str] = Field(default_factory=list)
    default_mentioned_mobile_list: list[str] = Field(default_factory=list)
    default_prompt: str = "你有新的任务，请处理"
    purchase_order_notify_enabled: bool = False
    updated_at: str | None = None


class WeComRobotSettingUpdateRequest(BaseModel):
    webhook_url: str = ""
    timeout_seconds: int = 30
    max_retries: int = 2
    rate_limit_per_minute: int = 20
    default_mentioned_user_ids: list[int] = Field(default_factory=list)
    default_mentioned_list: list[str] = Field(default_factory=list)
    default_mentioned_mobile_list: list[str] = Field(default_factory=list)
    default_prompt: str = ""
    purchase_order_notify_enabled: bool = False


class WeComRobotTestRequest(BaseModel):
    content: str = ""


class WeComRobotTestResponse(BaseModel):
    status: str = "success"
    message: str = ""


class TranslationProviderOptionDto(BaseModel):
    code: str
    name: str


class TranslationLanguageOptionDto(BaseModel):
    code: str
    label: str


class TranslationProviderSettingDto(BaseModel):
    provider: str = "baidu"
    provider_name: str = "百度翻译"
    enabled: bool = False
    app_id: str = ""
    has_secret_key: bool = False
    secret_key_masked: str = ""
    endpoint: str = ""
    source_language: str = "auto"
    timeout_seconds: int = 30
    max_retries: int = 2
    batch_size: int = 80
    batch_chars: int = 5000
    provider_options: dict = Field(default_factory=dict)
    last_test_at: str | None = None
    last_test_status: str = ""
    last_test_message: str = ""
    updated_at: str | None = None


class TranslationProviderSettingUpdateRequest(BaseModel):
    provider: str = "baidu"
    enabled: bool = False
    app_id: str = ""
    secret_key: str | None = None
    endpoint: str = ""
    source_language: str = "auto"
    timeout_seconds: int = 30
    max_retries: int = 2
    batch_size: int = 80
    batch_chars: int = 5000
    provider_options: dict = Field(default_factory=dict)


class TranslationProviderTestRequest(BaseModel):
    provider: str = "baidu"
    text: str = "测试翻译"
    target_language: str = "en"


class TranslationProviderTestResponse(BaseModel):
    status: str = "success"
    message: str = ""
    translated_text: str = ""


class TextTranslationRequest(BaseModel):
    text: str
    source_language: str = "auto"
    target_language: str = "en"


class TextTranslationResponse(BaseModel):
    status: str = "success"
    message: str = ""
    request_id: str = ""
    provider: str = "baidu"
    source_language: str = "auto"
    target_language: str = "en"
    translated_text: str = ""
    source_char_count: int = 0
    translated_char_count: int = 0


class ModelEndpointDto(BaseModel):
    id: int
    name: str
    base_url: str = ""
    api_key_masked: str = ""
    enabled: bool = True
    remark: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class ModelEndpointUpsertRequest(BaseModel):
    name: str
    base_url: str = ""
    api_key: str | None = None
    enabled: bool = True
    remark: str = ""


class ModelSettingDto(BaseModel):
    id: int
    name: str
    model: str
    endpoint_id: int | None = None
    endpoint_name: str = ""
    endpoint_enabled: bool = True
    url: str = ""
    is_default: bool = False
    supports_vision: bool = False
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class ModelSettingUpsertRequest(BaseModel):
    name: str
    model: str
    endpoint_id: int | None = None
    is_default: bool = False
    supports_vision: bool = False
    enabled: bool = True


class ModelConnectionTestResponse(BaseModel):
    model_setting_id: int
    model_setting_name: str
    model: str
    endpoint_name: str
    upstream_url: str
    duration_ms: int
    message: str = ""


class AiImageAssetDto(BaseModel):
    name: str
    url: str
    oss_object_key: str
    width: int
    height: int
    format: str
    size_bytes: int


class AiImageDownloadItem(BaseModel):
    object_key: str
    filename: str = ""


class AiImageBatchDownloadRequest(BaseModel):
    items: list[AiImageDownloadItem] = Field(default_factory=list)


class AiImageProcessResponse(BaseModel):
    operation: str
    model_setting_id: int | None = None
    model_setting_name: str = ""
    model: str = ""
    source_assets: list[AiImageAssetDto] = Field(default_factory=list)
    assets: list[AiImageAssetDto] = Field(default_factory=list)


class ExchangeRateDto(BaseModel):
    id: int
    rate_date: str
    currency_code: str
    currency_name: str = ""
    rate: str
    source_updated_at: str | None = None
    synced_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ExchangeRateListResponse(BaseModel):
    items: list[ExchangeRateDto]
    total: int
    page: int
    page_size: int
    currencies: list[str] = Field(default_factory=list)


class ExchangeRateSyncResult(BaseModel):
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    message: str = ""


class ExchangeRateCurrencySettingDto(BaseModel):
    id: int
    currency_code: str
    currency_name: str = ""
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class ExchangeRateCurrencySettingInput(BaseModel):
    currency_code: str
    currency_name: str = ""


class ExchangeRateCurrencySettingUpdateRequest(BaseModel):
    currencies: list[ExchangeRateCurrencySettingInput] = Field(default_factory=list)


class PlatformProductCatalogItemDto(BaseModel):
    id: int
    shop_id: int
    shop_name: str = ""
    platform: str
    product_id: int | None = None
    product_code: str = ""
    internal_product_name: str = ""
    platform_product_id: str = ""
    platform_sku: str = ""
    product_name: str = ""
    main_image_url: str = ""
    listing_status: str = ""
    warehouse_code: str = ""
    warehouse_name: str = ""
    fulfillment_type: str = ""
    logistics_type: str = ""
    available_stock: int = 0
    reserved_stock: int | None = None
    price_amount: str | None = None
    price_currency: str = "CNY"
    exchange_rate: str | None = None
    exchange_rate_date: str | None = None
    current_price_cny: str | None = None
    cost_cny: str | None = None
    commission_rate: str | None = None
    shipping_fee_cny: str | None = None
    target_margin_rate: str | None = None
    current_profit_cny: str | None = None
    current_margin_rate: str | None = None
    suggested_price_cny: str | None = None
    calculation_status: str = ""
    calculation_message: str = ""
    last_synced_at: str | None = None
    calculated_at: str | None = None
    is_active: bool = True


class PlatformProductCatalogListResponse(BaseModel):
    items: list[PlatformProductCatalogItemDto] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    summary: dict[str, int] = Field(default_factory=dict)


class PlatformProductCatalogOptionsResponse(BaseModel):
    shops: list[dict] = Field(default_factory=list)
    products: list[dict] = Field(default_factory=list)


CatalogSyncMode = Literal["full", "incremental"]


class PlatformProductCatalogSyncRequest(BaseModel):
    shop_ids: list[int] = Field(default_factory=list)
    mode: CatalogSyncMode = "full"


class PlatformProductCatalogSyncResult(BaseModel):
    shops: list[dict] = Field(default_factory=list)
    success: int = 0
    failed: int = 0
    synced: int = 0


class PlatformProductCatalogMappingRequest(BaseModel):
    product_id: int | None = None


class PlatformProductCatalogRecalculateRequest(BaseModel):
    item_ids: list[int] = Field(default_factory=list)


class PlatformProductCatalogRecalculateResult(BaseModel):
    recalculated: int = 0


class PlatformProductPricingRuleDto(BaseModel):
    id: int
    name: str
    platform: str
    shop_id: int | None = None
    shop_name: str = ""
    product_id: int | None = None
    product_name: str = ""
    warehouse_code: str = ""
    logistics_type: str = ""
    commission_rate: str = "0"
    base_shipping_fee_cny: str = "0"
    shipping_fee_per_kg_cny: str = "0"
    target_margin_rate: str = "0"
    price_increment_cny: str = "0.01"
    priority: int = 100
    enabled: bool = True
    remark: str = ""
    updated_at: str | None = None


class PlatformProductPricingRuleInput(BaseModel):
    name: str
    platform: str
    shop_id: int | None = None
    product_id: int | None = None
    warehouse_code: str = ""
    logistics_type: str = ""
    commission_rate: str | float = "0"
    base_shipping_fee_cny: str | float = "0"
    shipping_fee_per_kg_cny: str | float = "0"
    target_margin_rate: str | float = "0"
    price_increment_cny: str | float = "0.01"
    priority: int = 100
    enabled: bool = True
    remark: str = ""


class ScheduledTaskDto(BaseModel):
    id: int
    name: str
    task_type: str = "auto_order_pipeline"
    cron_expr: str
    enabled: bool = True
    settings: dict = Field(default_factory=dict)
    remark: str = ""
    last_run_at: str | None = None
    last_status: str = ""
    last_message: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class ScheduledTaskUpsertRequest(BaseModel):
    name: str
    task_type: str = "auto_order_pipeline"
    cron_expr: str
    enabled: bool = True
    settings: dict = Field(default_factory=dict)
    remark: str = ""


class ScheduledTaskRunDto(BaseModel):
    id: int
    scheduled_task_id: int | None = None
    task_type: str
    trigger_mode: str = ""
    status: str = ""
    summary: str = ""
    stats_json: dict = Field(default_factory=dict)
    pdf_export_platforms: list[str] = Field(default_factory=list)
    attempt_no: int = 0
    max_retry_count: int = 0
    parent_run_id: int | None = None
    original_run_id: int | None = None
    next_retry_at: str | None = None
    retry_reason: str = ""
    email_sent: bool = False
    email_error: str = ""
    started_at: str | None = None
    ended_at: str | None = None
    created_at: str | None = None


class ScheduledTaskRunListResponse(BaseModel):
    items: list[ScheduledTaskRunDto]
    total: int
    page: int
    page_size: int


class ScheduledTaskRunStepDto(BaseModel):
    id: int
    run_id: int
    step_code: str
    step_name: str
    status: str = ""
    message: str = ""
    stats_json: dict = Field(default_factory=dict)
    payload_json: dict = Field(default_factory=dict)
    started_at: str | None = None
    ended_at: str | None = None


class ScheduledTaskRunOrderDto(BaseModel):
    id: int
    run_id: int
    order_id: int
    platform_order_no: str = ""
    platform: str = ""
    document_type_name: str = ""
    purchase_order_id: int | None = None
    pdf_generated: bool = False
    pdf_file_path: str = ""
    has_label_file: bool = False
    label_file_path: str = ""
    printer_name: str = ""
    print_job_name: str = ""
    print_submitted: bool = False
    print_message: str = ""
    status_before: str = ""
    status_after: str = ""
    needs_reprint: bool = False
    error_message: str = ""
    created_at: str | None = None


class ScheduledTaskRunPlatformDto(BaseModel):
    run_id: int
    platform: str
    document_type_name: str = ""
    total_count: int = 0
    pdf_count: int = 0
    print_submitted_count: int = 0
    failed_count: int = 0
    reprintable_count: int = 0
    order_nos: list[str] = Field(default_factory=list)
    printer_names: list[str] = Field(default_factory=list)
    print_job_names: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    pdf_file_paths: list[str] = Field(default_factory=list)
    needs_reprint: bool = False
    print_submitted: bool = False


class ScheduledTaskRunPdfDownloadLinkDto(BaseModel):
    url: str
    filename: str
    expires_in_seconds: int
