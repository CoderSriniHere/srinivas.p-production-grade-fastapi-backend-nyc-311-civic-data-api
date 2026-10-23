from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health/ready")
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    checks = {"postgres": False, "redis": False}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        pass

    try:
        await redis_client.ping()
        checks["redis"] = True
    except Exception:
        pass

    all_ok = all(checks.values())
    if not all_ok:
        response.status_code = 503

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }