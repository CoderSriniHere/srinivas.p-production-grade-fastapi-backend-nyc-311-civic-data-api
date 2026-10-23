import json
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.metrics import report_jobs_total
from app.models import Complaint


async def _set_progress(redis_client, job_id: str, status: str, progress_pct: int):
    await redis_client.set(
        f"job:{job_id}:status",
        json.dumps({"status": status, "progress_pct": progress_pct}),
        ex=3600,
    )


async def generate_agency_report(ctx: dict, job_id: str, agency_code: str) -> dict:
    """
    ARQ task -- runs in the separate arq_worker process, not the web app.
    `ctx` is injected by ARQ automatically and carries the shared Redis pool.
    """
    redis_client = ctx["redis"]
    await _set_progress(redis_client, job_id, "in_progress", 10)

    try:
        async with AsyncSessionLocal() as db:
            resolution_hours = func.extract(
                "epoch", Complaint.closed_date - Complaint.created_date
            ) / 3600.0

            await _set_progress(redis_client, job_id, "in_progress", 50)

            result = await db.execute(
                select(
                    Complaint.borough,
                    Complaint.complaint_type,
                    func.avg(resolution_hours).label("avg_resolution_hours"),
                    func.count(Complaint.id).label("complaint_count"),
                )
                .where(Complaint.agency == agency_code, Complaint.closed_date.is_not(None))
                .group_by(Complaint.borough, Complaint.complaint_type)
            )
            rows = result.all()

            report_data = {
                "agency": agency_code,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "breakdown": [
                    {
                        "borough": r.borough,
                        "complaint_type": r.complaint_type,
                        "avg_resolution_hours": round(r.avg_resolution_hours, 2) if r.avg_resolution_hours else None,
                        "complaint_count": r.complaint_count,
                    }
                    for r in rows
                ],
            }
    except Exception:
        # Without this, a failing job leaves status stuck at "in_progress"
        # forever and the SSE stream in reports.py never stops polling.
        await _set_progress(redis_client, job_id, "failed", 0)
        report_jobs_total.labels(status="failed").inc()
        raise

    await redis_client.set(f"job:{job_id}:result", json.dumps(report_data), ex=86400)
    await _set_progress(redis_client, job_id, "complete", 100)
    report_jobs_total.labels(status="complete").inc()
    return {"job_id": job_id, "status": "complete"}