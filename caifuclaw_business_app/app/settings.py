# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from functools import lru_cache
import hashlib
import hmac
import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field

from .config_loader import optional, require


logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:9999",
    "http://localhost:9999",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
_INSECURE_DEFAULTS = {
    "change-me",
    "123456",
    "demo-sync-secret-not-for-production",
    "replace-with-at-least-32-random-characters",
    "replace_with_at_least_32_random_characters",
    "replace_with_at_least_12_random_characters",
    "generated-fernet-key",
}


class Settings(BaseModel):
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    sync_db_name: str

    sync_secret_key: str
    fernet_key: str
    internal_service_token: str = ""
    allowed_origins: list[str] = Field(default_factory=lambda: DEFAULT_ALLOWED_ORIGINS.copy())
    connector_runtime_url: str = "http://127.0.0.1:8100"
    public_base_url: str = "http://127.0.0.1:9999"
    oauth_authorization_session_minutes: int = 30

    label_storage_root: str
    admin_username: str
    admin_password: str
    order_sync_min_interval_seconds: int = 1200
    order_sync_startup_stagger_seconds: int = 15
    scheduler_enabled: bool = True
    scheduler_leader_lock_enabled: bool = True
    scheduler_heartbeat_interval_seconds: int = 60
    scheduler_watchdog_interval_seconds: int = 60
    sync_overdue_grace_seconds: int = 300
    sync_running_timeout_seconds: int = 1800
    sync_catchup_overlap_seconds: int = 3600
    sync_catchup_max_window_seconds: int = 259200
    status_sync_interval_seconds: int = 600
    oauth_token_maintenance_interval_seconds: int = 1800
    scheduled_task_retry_scan_interval_seconds: int = 60
    exchange_rate_sync_cron_exprs: list[str] = ["30,45 2 * * *", "0,15,30 3 * * *"]
    order_follow_up_export_enabled: bool = False
    order_follow_up_export_data_root: str = ""
    order_follow_up_export_workbook_name: str = "Order follow up 2026_caifuclaw.xlsx"
    order_follow_up_export_template_workbook_name: str = "Order follow up 2026.xlsx"
    order_follow_up_export_sync_dir: str = "result_data_sync"
    order_follow_up_export_backup_dir: str = "result_data_backup"
    order_follow_up_export_purchase_plan_dir: str = "pur_plan"
    order_follow_up_export_cutover_run_id: int = 0
    order_follow_up_export_max_attempts: int = 3
    order_follow_up_export_retry_delay_seconds: int = 300
    order_follow_up_export_worker_poll_seconds: int = 5
    order_follow_up_export_worker_idle_seconds: int = 15
    order_follow_up_export_lease_seconds: int = 1800
    order_follow_up_export_backup_retention_days: int = 90
    order_follow_up_export_dedupe_existing_workbook: bool = True
    order_follow_up_export_logistics_channel_fallbacks: dict[str, str] = {
        "ozon": "ozon线上发货",
        "joom": "Joom Logistics",
        "joom_logistics": "Joom Logistics",
        "mercadolibre": "Mercadolibre跨境发货",
    }
    order_follow_up_export_recalculate_engine: str = "auto"
    order_follow_up_export_recalculate_command: str = ""
    order_follow_up_export_recalculate_timeout_seconds: int = 300
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.sync_db_name}"
        )

    @property
    def label_storage_path(self) -> Path:
        path = Path(self.label_storage_root)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        return path

    @property
    def order_follow_up_export_data_path(self) -> Path:
        path = Path(self.order_follow_up_export_data_root).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        return path

    @property
    def bsi_callback_token(self) -> str:
        return hmac.new(
            self.sync_secret_key.encode("utf-8"),
            b"bsi-sdms-callback",
            hashlib.sha256,
        ).hexdigest()


@lru_cache
def get_settings() -> Settings:
    return Settings(
        postgres_host=require("postgres", "host"),
        postgres_port=require("postgres", "port"),
        postgres_user=require("postgres", "user"),
        postgres_password=require("postgres", "password"),
        sync_db_name=require("databases", "sync"),
        sync_secret_key=require("security", "sync_secret_key"),
        fernet_key=optional("security", "fernet_key", ""),
        internal_service_token=str(optional("security", "internal_service_token", "") or ""),
        allowed_origins=list(optional("security", "allowed_origins", DEFAULT_ALLOWED_ORIGINS)),
        connector_runtime_url=optional("services", "connector_runtime_url", "http://127.0.0.1:8100"),
        public_base_url=str(optional("services", "public_base_url", "http://127.0.0.1:9999")).rstrip("/"),
        oauth_authorization_session_minutes=int(optional("oauth", "authorization_session_minutes", 30)),
        label_storage_root=require("storage", "label_storage_root"),
        admin_username=require("sync_admin", "username"),
        admin_password=require("sync_admin", "password"),
        order_sync_min_interval_seconds=int(optional("scheduler", "order_sync_min_interval_seconds", 1200)),
        order_sync_startup_stagger_seconds=int(optional("scheduler", "order_sync_startup_stagger_seconds", 15)),
        scheduler_enabled=bool(optional("scheduler", "scheduler_enabled", True)),
        scheduler_leader_lock_enabled=bool(optional("scheduler", "scheduler_leader_lock_enabled", True)),
        scheduler_heartbeat_interval_seconds=int(optional("scheduler", "scheduler_heartbeat_interval_seconds", 60)),
        scheduler_watchdog_interval_seconds=int(optional("scheduler", "scheduler_watchdog_interval_seconds", 60)),
        sync_overdue_grace_seconds=int(optional("scheduler", "sync_overdue_grace_seconds", 300)),
        sync_running_timeout_seconds=int(optional("scheduler", "sync_running_timeout_seconds", 1800)),
        sync_catchup_overlap_seconds=int(optional("scheduler", "sync_catchup_overlap_seconds", 3600)),
        sync_catchup_max_window_seconds=int(optional("scheduler", "sync_catchup_max_window_seconds", 259200)),
        status_sync_interval_seconds=int(optional("scheduler", "status_sync_interval_seconds", 600)),
        oauth_token_maintenance_interval_seconds=int(optional("scheduler", "oauth_token_maintenance_interval_seconds", 1800)),
        scheduled_task_retry_scan_interval_seconds=int(optional("scheduler", "scheduled_task_retry_scan_interval_seconds", 60)),
        exchange_rate_sync_cron_exprs=list(
            optional("scheduler", "exchange_rate_sync_cron_exprs", ["30,45 2 * * *", "0,15,30 3 * * *"])
        ),
        order_follow_up_export_enabled=bool(optional("order_follow_up_export", "enabled", False)),
        order_follow_up_export_data_root=str(optional("order_follow_up_export", "data_root", "")),
        order_follow_up_export_workbook_name=str(
            optional("order_follow_up_export", "workbook_name", "Order follow up 2026_caifuclaw.xlsx")
        ),
        order_follow_up_export_template_workbook_name=str(
            optional("order_follow_up_export", "template_workbook_name", "Order follow up 2026.xlsx")
        ),
        order_follow_up_export_sync_dir=str(optional("order_follow_up_export", "sync_dir", "result_data_sync")),
        order_follow_up_export_backup_dir=str(optional("order_follow_up_export", "backup_dir", "result_data_backup")),
        order_follow_up_export_purchase_plan_dir=str(
            optional("order_follow_up_export", "purchase_plan_dir", "pur_plan")
        ),
        order_follow_up_export_cutover_run_id=int(optional("order_follow_up_export", "cutover_run_id", 0)),
        order_follow_up_export_max_attempts=int(optional("order_follow_up_export", "max_attempts", 3)),
        order_follow_up_export_retry_delay_seconds=int(
            optional("order_follow_up_export", "retry_delay_seconds", 300)
        ),
        order_follow_up_export_worker_poll_seconds=int(
            optional("order_follow_up_export", "worker_poll_seconds", 5)
        ),
        order_follow_up_export_worker_idle_seconds=int(
            optional("order_follow_up_export", "worker_idle_seconds", 15)
        ),
        order_follow_up_export_lease_seconds=int(optional("order_follow_up_export", "lease_seconds", 1800)),
        order_follow_up_export_backup_retention_days=int(
            optional("order_follow_up_export", "backup_retention_days", 90)
        ),
        order_follow_up_export_dedupe_existing_workbook=bool(
            optional("order_follow_up_export", "dedupe_existing_workbook", True)
        ),
        order_follow_up_export_logistics_channel_fallbacks=dict(
            optional(
                "order_follow_up_export",
                "logistics_channel_fallbacks",
                {
                    "ozon": "ozon线上发货",
                    "joom": "Joom Logistics",
                    "joom_logistics": "Joom Logistics",
                    "mercadolibre": "Mercadolibre跨境发货",
                },
            )
        ),
        order_follow_up_export_recalculate_engine=str(
            optional("order_follow_up_export", "recalculate_engine", "auto")
        ),
        order_follow_up_export_recalculate_command=str(
            optional("order_follow_up_export", "recalculate_command", "")
        ),
        order_follow_up_export_recalculate_timeout_seconds=int(
            optional("order_follow_up_export", "recalculate_timeout_seconds", 300)
        ),
    )


def validate_security_settings(settings: Settings) -> None:
    """Reject placeholder secrets in production and warn during local development."""
    insecure_fields: list[str] = []
    if str(settings.postgres_password).strip().lower() in _INSECURE_DEFAULTS:
        insecure_fields.append("postgres.password")
    if str(settings.sync_secret_key).strip().lower() in _INSECURE_DEFAULTS:
        insecure_fields.append("security.sync_secret_key")
    elif len(str(settings.sync_secret_key).strip()) < 32:
        insecure_fields.append("security.sync_secret_key (minimum 32 characters)")
    if str(settings.admin_password).strip().lower() in _INSECURE_DEFAULTS:
        insecure_fields.append("sync_admin.password")
    elif len(str(settings.admin_password)) < 12:
        insecure_fields.append("sync_admin.password (minimum 12 characters)")
    if len(str(settings.internal_service_token).strip()) < 32:
        insecure_fields.append("security.internal_service_token (minimum 32 characters)")
    if not str(settings.fernet_key).strip():
        insecure_fields.append("security.fernet_key")

    strict = (
        os.getenv("CAIFUCLAW_AI_REQUIRE_SECURE_CONFIG", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("CAIFUCLAW_ERP_REQUIRE_SECURE_CONFIG", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("CAIFUCLAW_AI_ENV", "").strip().lower() in {"prod", "production"}
        or os.getenv("CAIFUCLAW_ERP_ENV", "").strip().lower() in {"prod", "production"}
    )
    if insecure_fields and strict:
        fields = ", ".join(insecure_fields)
        raise RuntimeError(f"Secure configuration required; replace placeholder values for: {fields}")
    if insecure_fields:
        logger.warning(
            "Development configuration contains insecure or missing values: %s. "
            "Set CAIFUCLAW_AI_REQUIRE_SECURE_CONFIG=1 in production.",
            ", ".join(insecure_fields),
        )
