from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import LocalUser, UserTablePreference
from ..contracts.table_preferences import TablePreferenceDto, TablePreferenceUpsertRequest


def _table_preference_dto(
    table_key: str,
    row: UserTablePreference | None = None,
) -> TablePreferenceDto:
    return TablePreferenceDto(
        id=row.id if row else None,
        table_key=table_key,
        config_json=row.config_json if row else None,
        created_at=row.created_at.isoformat() if row and row.created_at else None,
        updated_at=row.updated_at.isoformat() if row and row.updated_at else None,
    )


def create_table_preferences_router(
    current_user_dependency: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/table-preferences", tags=["table-preferences"])

    @router.get("/{table_key:path}", response_model=TablePreferenceDto)
    def get_table_preference(
        table_key: str,
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> TablePreferenceDto:
        row = db.scalar(
            select(UserTablePreference).where(
                UserTablePreference.user_id == user.id,
                UserTablePreference.table_key == table_key,
            )
        )
        return _table_preference_dto(table_key, row)

    @router.put("/{table_key:path}", response_model=TablePreferenceDto)
    def upsert_table_preference(
        table_key: str,
        payload: TablePreferenceUpsertRequest,
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> TablePreferenceDto:
        row = db.scalar(
            select(UserTablePreference).where(
                UserTablePreference.user_id == user.id,
                UserTablePreference.table_key == table_key,
            )
        )
        now = datetime.utcnow()
        if row:
            row.config_json = payload.config_json
            row.updated_at = now
        else:
            row = UserTablePreference(
                user_id=user.id,
                table_key=table_key,
                config_json=payload.config_json,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        db.commit()
        db.refresh(row)
        return _table_preference_dto(table_key, row)

    @router.delete("/{table_key:path}")
    def delete_table_preference(
        table_key: str,
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        row = db.scalar(
            select(UserTablePreference).where(
                UserTablePreference.user_id == user.id,
                UserTablePreference.table_key == table_key,
            )
        )
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True}

    return router
