import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import CurrentUser, get_arq_pool, get_redis, require_scope
from app.metrics import report_jobs_total

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", status_code=202)
async def submit_report(
    user: CurrentUser = Depends(require_scope("complaints:read")),
    arq_pool=Depends(get_arq_pool),
):
    job_id = str(uuid.uuid4())
    await arq_pool.enqueue_job("generate_agency_report", job_id, user.agency_code, _job_id=job_id)
    report_jobs_total.labels(status="queued").inc()
    return {"job_id": job_id, "status": "queued", "submitted_at": datetime.now(timezone.utc).isoformat()}


@router.get("/{job_id}")
async def get_report_status(
    job_id: str,
    user: CurrentUser = Depends(require_scope("complaints:read")),
    redis_client: redis.Redis = Depends(get_redis),
):
    raw = await redis_client.get(f"job:{job_id}:status")
    status_data = json.loads(raw) if raw else {"status": "queued", "progress_pct": 0}
    result_exists = await redis_client.exists(f"job:{job_id}:result")
    return {"job_id": job_id, **status_data, "result_available": bool(result_exists)}


@router.get("/{job_id}/result")
async def get_report_result(
    job_id: str,
    user: CurrentUser = Depends(require_scope("complaints:export")),
    redis_client: redis.Redis = Depends(get_redis),
):
    raw = await redis_client.get(f"job:{job_id}:result")
    if raw is None:
        raise HTTPException(status_code=404, detail="Report result not ready or not found")
    return json.loads(raw)

import asyncio
from sse_starlette.sse import EventSourceResponse


@router.get("/{job_id}/stream")
async def stream_report_progress(
    job_id: str,
    user: CurrentUser = Depends(require_scope("complaints:read")),
    redis_client: redis.Redis = Depends(get_redis),
):
    async def event_generator():
        while True:
            raw = await redis_client.get(f"job:{job_id}:status")
            status_data = json.loads(raw) if raw else {"status": "queued", "progress_pct": 0}
            yield {"event": "progress", "data": json.dumps(status_data)}
            if status_data["status"] in ("complete", "failed"):
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())