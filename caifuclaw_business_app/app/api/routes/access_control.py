# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from collections.abc import Callable, Collection, Sequence
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import LocalUser, Role, UserRole
from ...schemas import (
    MenuDto,
    RoleCreateRequest,
    RoleDto,
    RoleUpdateRequest,
    UserCreateRequest,
    UserDto,
    UserOptionDto,
    UserResetPasswordRequest,
    UserUpdateRequest,
)
from ...security import hash_password


def create_access_control_router(
    *,
    current_user_dependency: Callable[..., Any],
    require_admin_dependency: Callable[..., Any],
    menu_definitions: Sequence[dict],
    enabled_buyer_users: Callable[[Session], list[LocalUser]],
    user_option_dto: Callable[[LocalUser], UserOptionDto],
    role_dto: Callable[[Role, Session], RoleDto],
    roles_by_payload: Callable[[list[int] | None, int | None, Session], list[Role]],
    normalize_wecom_mobile: Callable[[str | None], str],
    set_user_roles: Callable[[LocalUser, list[Role], Session], None],
    user_dto: Callable[[LocalUser, Session], UserDto],
    set_role_menus: Callable[[Role, list[str], Session], None],
    roles_for_user: Callable[..., list[Role]],
    admin_role_code: str,
    hidden_role_code: str,
    reserved_role_codes: Collection[str],
) -> APIRouter:
    router = APIRouter(tags=["access-control"])

    @router.get("/api/v1/menus", response_model=list[MenuDto])
    def list_menus(_: LocalUser = Depends(require_admin_dependency)) -> list[MenuDto]:
        return [MenuDto(**item) for item in menu_definitions]

    @router.get("/api/v1/user-options", response_model=list[UserOptionDto])
    def list_user_options(
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> list[UserOptionDto]:
        return [user_option_dto(row) for row in enabled_buyer_users(db)]

    @router.get("/api/v1/roles", response_model=list[RoleDto])
    def list_roles(
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> list[RoleDto]:
        rows = db.scalars(
            select(Role)
            .where(Role.code != hidden_role_code)
            .order_by(desc(Role.is_system), asc(Role.id))
        ).all()
        return [role_dto(row, db) for row in rows]

    @router.post("/api/v1/roles", response_model=RoleDto)
    def create_role(
        payload: RoleCreateRequest,
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> RoleDto:
        code = payload.code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="角色编码不能为空")
        if not code.replace("_", "").replace("-", "").isalnum():
            raise HTTPException(status_code=400, detail="角色编码只能包含字母、数字、下划线或短横线")
        if code in reserved_role_codes:
            raise HTTPException(status_code=400, detail="系统角色编码已存在")
        if db.scalar(select(Role).where(Role.code == code)):
            raise HTTPException(status_code=400, detail="角色编码已存在")
        role = Role(
            code=code,
            name=payload.name.strip() or code,
            description=payload.description.strip(),
            enabled=payload.enabled,
            is_system=False,
        )
        db.add(role)
        db.flush()
        set_role_menus(role, payload.menus, db)
        db.commit()
        db.refresh(role)
        return role_dto(role, db)

    @router.put("/api/v1/roles/{role_id:int}", response_model=RoleDto)
    def update_role(
        role_id: int,
        payload: RoleUpdateRequest,
        admin: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> RoleDto:
        role = db.get(Role, role_id)
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        if role.code == admin_role_code:
            raise HTTPException(status_code=400, detail="管理员角色不允许修改")
        if any(item.id == role.id for item in roles_for_user(admin, db)) and not payload.enabled:
            raise HTTPException(status_code=400, detail="不能停用当前账号所属角色")
        role.name = payload.name.strip() or role.code
        role.description = payload.description.strip()
        role.enabled = payload.enabled
        role.updated_at = datetime.utcnow()
        set_role_menus(role, payload.menus, db)
        db.commit()
        db.refresh(role)
        return role_dto(role, db)

    @router.delete("/api/v1/roles/{role_id:int}")
    def delete_role(
        role_id: int,
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        role = db.get(Role, role_id)
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        if role.code == admin_role_code:
            raise HTTPException(status_code=400, detail="管理员角色不允许删除")
        if db.scalar(select(UserRole.id).where(UserRole.role_id == role.id).limit(1)) or db.scalar(
            select(LocalUser.id).where(LocalUser.role_id == role.id).limit(1)
        ):
            raise HTTPException(status_code=400, detail="角色已被用户使用，不能删除")
        db.delete(role)
        db.commit()
        return {"ok": True}

    @router.get("/api/v1/users", response_model=list[UserDto])
    def list_users(
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> list[UserDto]:
        rows = db.scalars(select(LocalUser).order_by(asc(LocalUser.id))).all()
        return [user_dto(row, db) for row in rows]

    @router.post("/api/v1/users", response_model=UserDto)
    def create_user(
        payload: UserCreateRequest,
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> UserDto:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="用户名不能为空")
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        if db.scalar(select(LocalUser).where(LocalUser.username == username)):
            raise HTTPException(status_code=400, detail="用户名已存在")
        roles = roles_by_payload(payload.role_ids, payload.role_id, db)
        row = LocalUser(
            username=username,
            password_hash=hash_password(payload.password),
            display_name=(payload.display_name or "").strip(),
            wecom_mobile=normalize_wecom_mobile(payload.wecom_mobile),
            role_id=roles[0].id,
            enabled=payload.enabled,
        )
        db.add(row)
        db.flush()
        set_user_roles(row, roles, db)
        db.commit()
        db.refresh(row)
        return user_dto(row, db)

    @router.put("/api/v1/users/{user_id:int}", response_model=UserDto)
    def update_user(
        user_id: int,
        payload: UserUpdateRequest,
        admin: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> UserDto:
        row = db.get(LocalUser, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        roles = roles_by_payload(payload.role_ids, payload.role_id, db)
        if row.id == admin.id and (
            not any(role.code == admin_role_code for role in roles) or not payload.enabled
        ):
            raise HTTPException(
                status_code=400,
                detail="不能取消当前管理员账号的管理员角色或禁用当前账号",
            )
        row.display_name = (payload.display_name or "").strip()
        row.wecom_mobile = normalize_wecom_mobile(payload.wecom_mobile)
        row.enabled = payload.enabled
        set_user_roles(row, roles, db)
        db.commit()
        db.refresh(row)
        return user_dto(row, db)

    @router.post("/api/v1/users/{user_id:int}/reset-password", response_model=UserDto)
    def reset_user_password(
        user_id: int,
        payload: UserResetPasswordRequest,
        _: LocalUser = Depends(require_admin_dependency),
        db: Session = Depends(get_db),
    ) -> UserDto:
        row = db.get(LocalUser, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        if len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        row.password_hash = hash_password(payload.password)
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return user_dto(row, db)

    return router
