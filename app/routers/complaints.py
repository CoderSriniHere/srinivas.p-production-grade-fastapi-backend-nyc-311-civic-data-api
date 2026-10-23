from datetime import datetime
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, CurrentUser, get_redis, require_scope
from app.database import get_db
from app.models import AuditLog, Complaint
from app.repositories.complaint_repository import get_repo, ComplaintRepository
from app.metrics import cache_hits_total, cache_misses_total
from app.logging_config import get_logger
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintDetail,
    ComplaintStatusUpdate,
    ComplaintSummary,
    PaginatedComplaints,
)
from app.services.cache import (
    cache_get,
    cache_set,
    complaints_list_cache_key,
    invalidate_agency_complaint_cache,
)

router = APIRouter(tags=["complaints"])
logger = get_logger()


async def _write_audit_log(db: AsyncSession, user_id: str, query_params: dict, result_count: int):
    entry = AuditLog(user_id=user_id, query_params=query_params, result_count=result_count)
    db.add(entry)
    await db.commit()


@router.get("/complaints", response_model=PaginatedComplaints)
async def list_complaints(
    background_tasks: BackgroundTasks,
    response: Response,
    borough: str | None = None,
    complaint_type: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = 1,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
    repo: ComplaintRepository = Depends(get_repo),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    filters = {
        "borough": borough,
        "complaint_type": complaint_type,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
        "page": page,
        "limit": limit,
    }
    logger.info("list_complaints_called", agency_code=user.agency_code, user_id=user.user_id)
    cache_key = complaints_list_cache_key(user.agency_code, filters)
    cached = await cache_get(redis_client, cache_key)

    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        cache_hits_total.labels(endpoint="/complaints").inc()
        background_tasks.add_task(
            _write_audit_log, db, user.user_id, filters, cached["total"]
        )
        return cached

    response.headers["X-Cache"] = "MISS"
    cache_misses_total.labels(endpoint="/complaints").inc()
    complaints, total = await repo.list_paginated(user.agency_code, **filters)

    payload = {
        "items": [ComplaintSummary.model_validate(c).model_dump() for c in complaints],
        "page": page,
        "limit": limit,
        "total": total,
    }
    await cache_set(redis_client, cache_key, payload, ttl_seconds=60)

    background_tasks.add_task(_write_audit_log, db, user.user_id, filters, total)
    return payload


@router.get("/complaints/export")
async def export_complaints_csv(
    borough: str | None = None,
    complaint_type: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    user: CurrentUser = Depends(require_scope("complaints:export")),
    repo: ComplaintRepository = Depends(get_repo),
):
    async def row_generator():
        yield "id,unique_key,agency,complaint_type,status,borough,created_date\n"

        batch_size = 500
        page = 1
        while True:
            complaints, _ = await repo.list_paginated(
                user.agency_code,
                borough=borough,
                complaint_type=complaint_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
                page=page,
                limit=batch_size,
            )
            if not complaints:
                break
            for c in complaints:
                yield f"{c.id},{c.unique_key},{c.agency},{c.complaint_type},{c.status},{c.borough},{c.created_date.isoformat()}\n"
            if len(complaints) < batch_size:
                break
            page += 1

    filename = f"complaints_{datetime.utcnow().date().isoformat()}.csv"
    return StreamingResponse(
        row_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/complaints/{complaint_id}", response_model=ComplaintDetail)
async def get_complaint(
    complaint_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    repo: ComplaintRepository = Depends(get_repo),
):
    complaint = await repo.get_by_id(complaint_id, user.agency_code)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.patch("/complaints/{complaint_id}/status", response_model=ComplaintDetail)
async def update_complaint_status(
    complaint_id: UUID,
    payload: ComplaintStatusUpdate,
    user: CurrentUser = Depends(require_scope("complaints:write")),
    repo: ComplaintRepository = Depends(get_repo),
    redis_client: redis.Redis = Depends(get_redis),
):
    complaint = await repo.update_status(complaint_id, user.agency_code, payload.status)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    await invalidate_agency_complaint_cache(redis_client, user.agency_code)
    return complaint


@router.post("/complaints", response_model=ComplaintDetail, status_code=201)
async def create_complaint(
    payload: ComplaintCreate,
    user: CurrentUser = Depends(require_scope("complaints:write")),
    repo: ComplaintRepository = Depends(get_repo),
    redis_client: redis.Redis = Depends(get_redis),
):
    complaint = await repo.create(
        agency_code=user.agency_code,
        unique_key=payload.unique_key,
        complaint_type=payload.complaint_type,
        borough=payload.borough,
        descriptor=payload.descriptor,
        incident_zip=payload.incident_zip,
        incident_address=payload.incident_address,
        created_date=payload.created_date,
        status="Open",
    )
    await invalidate_agency_complaint_cache(redis_client, user.agency_code)
    return complaint


@router.get("/complaint-types")
async def get_complaint_types(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    cache_key = "complaint-types:all"
    cached = await cache_get(redis_client, cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        cache_hits_total.labels(endpoint="/complaint-types").inc()
        return {"complaint_types": cached}

    response.headers["X-Cache"] = "MISS"
    cache_misses_total.labels(endpoint="/complaint-types").inc()
    result = await db.execute(select(Complaint.complaint_type).distinct())
    types = [row[0] for row in result.all()]
    await cache_set(redis_client, cache_key, types, ttl_seconds=3600)
    return {"complaint_types": types}


@router.get("/boroughs/stats")
async def get_borough_stats(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    cache_key = "boroughs:stats"
    cached = await cache_get(redis_client, cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        cache_hits_total.labels(endpoint="/boroughs/stats").inc()
        return {"stats": cached}

    response.headers["X-Cache"] = "MISS"
    cache_misses_total.labels(endpoint="/boroughs/stats").inc()
    result = await db.execute(
        select(Complaint.borough, func.count(Complaint.id).label("total"))
        .group_by(Complaint.borough)
    )
    stats = [{"borough": row.borough, "total": row.total} for row in result.all()]
    await cache_set(redis_client, cache_key, stats, ttl_seconds=300)
    return {"stats": stats}
