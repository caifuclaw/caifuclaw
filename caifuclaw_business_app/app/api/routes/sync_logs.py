from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Integer, and_, desc, func, or_, select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import ApiRequestLog, LocalUser
from ...schemas import (
    ApiRequestLogDto,
    ApiRequestLogListResponse,
    ApiRequestLogSummaryDto,
    ApiRequestLogSummaryListResponse,
)


def _api_request_log_conditions(
    platform: str = "",
    account_id: str = "",
    operation: str = "",
    status_value: str = "",
    keyword: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list:
    conditions = []
    if platform:
        conditions.append(ApiRequestLog.platform == platform)
    account_id_term = account_id.strip()
    if account_id_term:
        conditions.append(ApiRequestLog.account_id.ilike(f"%{account_id_term}%"))
    if operation:
        conditions.append(ApiRequestLog.operation == operation)
    if status_value:
        conditions.append(ApiRequestLog.status == status_value)
    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date_from 格式不正确") from exc
        conditions.append(ApiRequestLog.created_at >= parsed_from)
    if date_to:
        try:
            parsed_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date_to 格式不正确") from exc
        conditions.append(ApiRequestLog.created_at <= parsed_to)
    keyword_term = keyword.strip()
    if keyword_term:
        pattern = f"%{keyword_term}%"
        conditions.append(
            or_(
                ApiRequestLog.url.ilike(pattern),
                ApiRequestLog.account_id.ilike(pattern),
                ApiRequestLog.operation.ilike(pattern),
                ApiRequestLog.error_message.ilike(pattern),
            )
        )
    return conditions


def _api_request_log_dto(row: ApiRequestLog) -> ApiRequestLogDto:
    return ApiRequestLogDto(
        id=row.id,
        platform=row.platform,
        account_id=row.account_id,
        operation=row.operation or "",
        status=row.status or ("failed" if row.error_message else "success"),
        request_id=row.request_id or "",
        method=row.method,
        url=row.url,
        request_body=row.request_body,
        response_status=row.response_status,
        response_body=row.response_body,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
        extra=row.extra or {},
        log_date=row.log_date,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _api_request_log_list_dto(row) -> ApiRequestLogDto:
    return ApiRequestLogDto(
        id=row.id,
        platform=row.platform,
        account_id=row.account_id,
        operation=row.operation or "",
        status=row.status or ("failed" if row.error_message else "success"),
        request_id=row.request_id or "",
        method=row.method,
        url=row.url,
        request_body=None,
        response_status=row.response_status,
        response_body=None,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
        extra={},
        log_date=row.log_date,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def create_sync_logs_router(
    *,
    current_user_dependency: Callable[..., Any],
    iso_formatter: Callable[[datetime | None], str | None],
) -> APIRouter:
    router = APIRouter(tags=["sync-api-logs"])

    @router.get("/api/v1/sync-api-logs", response_model=ApiRequestLogListResponse)
    def list_sync_api_logs(
        platform: str = "",
        account_id: str = "",
        operation: str = "",
        status_value: str = Query("", alias="status"),
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> ApiRequestLogListResponse:
        conditions = _api_request_log_conditions(
            platform,
            account_id,
            operation,
            status_value,
            keyword,
            date_from,
            date_to,
        )
        where_clause = and_(*conditions) if conditions else True
        total = db.scalar(select(func.count()).select_from(ApiRequestLog).where(where_clause)) or 0
        rows = db.execute(
            select(
                ApiRequestLog.id,
                ApiRequestLog.platform,
                ApiRequestLog.account_id,
                ApiRequestLog.operation,
                ApiRequestLog.status,
                ApiRequestLog.request_id,
                ApiRequestLog.method,
                ApiRequestLog.url,
                ApiRequestLog.response_status,
                ApiRequestLog.error_message,
                ApiRequestLog.duration_ms,
                ApiRequestLog.log_date,
                ApiRequestLog.created_at,
            )
            .where(where_clause)
            .order_by(ApiRequestLog.created_at.desc(), ApiRequestLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ApiRequestLogListResponse(
            items=[_api_request_log_list_dto(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @router.get("/api/v1/sync-api-logs/{log_id}", response_model=ApiRequestLogDto)
    def get_sync_api_log(
        log_id: int,
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> ApiRequestLogDto:
        row = db.get(ApiRequestLog, log_id)
        if not row:
            raise HTTPException(status_code=404, detail="日志不存在")
        return _api_request_log_dto(row)

    @router.get("/api/v1/sync-api-logs-summary", response_model=ApiRequestLogSummaryListResponse)
    def summarize_sync_api_logs(
        platform: str = "",
        account_id: str = "",
        operation: str = "",
        status_value: str = Query("", alias="status"),
        keyword: str = "",
        date_from: str = "",
        date_to: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        limit: int | None = Query(None, ge=1, le=500),
        _: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> ApiRequestLogSummaryListResponse:
        if limit is not None:
            page = 1
            page_size = limit
        conditions = _api_request_log_conditions(
            platform,
            account_id,
            operation,
            status_value,
            keyword,
            date_from,
            date_to,
        )
        where_clause = and_(*conditions) if conditions else True
        summary_stmt = (
            select(
                ApiRequestLog.log_date,
                ApiRequestLog.platform,
                ApiRequestLog.account_id,
                ApiRequestLog.operation,
                ApiRequestLog.url,
                func.max(ApiRequestLog.created_at).label("last_created_at"),
                func.count(ApiRequestLog.id).label("total"),
                func.sum(func.cast(ApiRequestLog.status == "success", Integer)).label("success_count"),
                func.sum(func.cast(ApiRequestLog.status == "failed", Integer)).label("failed_count"),
                func.avg(ApiRequestLog.duration_ms).label("avg_duration_ms"),
                func.max(ApiRequestLog.duration_ms).label("max_duration_ms"),
            )
            .where(where_clause)
            .group_by(
                ApiRequestLog.log_date,
                ApiRequestLog.platform,
                ApiRequestLog.account_id,
                ApiRequestLog.operation,
                ApiRequestLog.url,
            )
        )
        summary_rows = summary_stmt.subquery()
        total = db.scalar(select(func.count()).select_from(summary_rows)) or 0
        rows = db.execute(
            select(summary_rows)
            .order_by(desc("last_created_at"), desc("total"))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ApiRequestLogSummaryListResponse(
            items=[
                ApiRequestLogSummaryDto(
                    log_date=row.log_date,
                    last_created_at=iso_formatter(row.last_created_at) or "",
                    platform=row.platform,
                    account_id=row.account_id,
                    operation=row.operation or "",
                    url=row.url or "",
                    total=int(row.total or 0),
                    success_count=int(row.success_count or 0),
                    failed_count=int(row.failed_count or 0),
                    avg_duration_ms=(
                        int(row.avg_duration_ms) if row.avg_duration_ms is not None else None
                    ),
                    max_duration_ms=(
                        int(row.max_duration_ms) if row.max_duration_ms is not None else None
                    ),
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    return router
