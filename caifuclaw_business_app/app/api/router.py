from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from ..models import LocalUser, Role
from ..schemas import RoleDto, UserDto, UserOptionDto
from .routes.access_control import create_access_control_router
from .routes.auth import create_auth_router
from .routes.dashboard import DashboardRouteServices, create_dashboard_router
from .routes.sync_logs import create_sync_logs_router
from .routes.sync_settings import SyncSettingsRouteServices, create_sync_settings_router
from .routes.table_preferences import create_table_preferences_router
from .routes.traffic_analytics import create_traffic_analytics_router


def create_api_router(
    *,
    current_user_dependency: Callable[..., Any],
    roles_for_user: Callable[..., list[Role]],
    menu_codes_for_user: Callable[[LocalUser, Any], list[str]],
    admin_role_code: str,
    require_admin_dependency: Callable[..., Any],
    menu_definitions: list[dict],
    enabled_buyer_users: Callable[[Any], list[LocalUser]],
    user_option_dto: Callable[[LocalUser], UserOptionDto],
    role_dto: Callable[[Role, Any], RoleDto],
    roles_by_payload: Callable[[list[int] | None, int | None, Any], list[Role]],
    normalize_wecom_mobile: Callable[[str | None], str],
    set_user_roles: Callable[[LocalUser, list[Role], Any], None],
    user_dto: Callable[[LocalUser, Any], UserDto],
    set_role_menus: Callable[[Role, list[str], Any], None],
    hidden_role_code: str,
    reserved_role_codes: set[str],
    iso_formatter: Callable[[Any], str | None],
    dashboard_services: DashboardRouteServices,
    sync_settings_services: SyncSettingsRouteServices,
) -> APIRouter:
    router = APIRouter()
    router.include_router(
        create_auth_router(
            current_user_dependency=current_user_dependency,
            roles_for_user=roles_for_user,
            menu_codes_for_user=menu_codes_for_user,
            admin_role_code=admin_role_code,
        )
    )
    router.include_router(
        create_access_control_router(
            current_user_dependency=current_user_dependency,
            require_admin_dependency=require_admin_dependency,
            menu_definitions=menu_definitions,
            enabled_buyer_users=enabled_buyer_users,
            user_option_dto=user_option_dto,
            role_dto=role_dto,
            roles_by_payload=roles_by_payload,
            normalize_wecom_mobile=normalize_wecom_mobile,
            set_user_roles=set_user_roles,
            user_dto=user_dto,
            set_role_menus=set_role_menus,
            roles_for_user=roles_for_user,
            admin_role_code=admin_role_code,
            hidden_role_code=hidden_role_code,
            reserved_role_codes=reserved_role_codes,
        )
    )
    router.include_router(create_table_preferences_router(current_user_dependency))
    router.include_router(
        create_sync_logs_router(
            current_user_dependency=current_user_dependency,
            iso_formatter=iso_formatter,
        )
    )
    router.include_router(
        create_traffic_analytics_router(current_user_dependency=current_user_dependency)
    )
    router.include_router(
        create_dashboard_router(
            current_user_dependency=current_user_dependency,
            require_admin_dependency=require_admin_dependency,
            services=dashboard_services,
        )
    )
    router.include_router(
        create_sync_settings_router(
            current_user_dependency=current_user_dependency,
            services=sync_settings_services,
        )
    )
    return router
