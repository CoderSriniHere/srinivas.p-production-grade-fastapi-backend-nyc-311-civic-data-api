import json
from typing import Any

import redis.asyncio as redis


async def cache_get(client: redis.Redis, key: str) -> Any | None:
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(client: redis.Redis, key: str, value: Any, ttl_seconds: int) -> None:
    await client.set(key, json.dumps(value, default=str), ex=ttl_seconds)

def complaints_list_cache_key(agency_code: str, filters: dict[str, Any] | None = None) -> str:
    filters_part = ""
    if filters:
        encoded = ",".join(f"{k}={v}" for k, v in sorted(filters.items()) if v is not None)
        filters_part = f":{encoded}"
    return f"complaints:list:{agency_code}{filters_part}"


async def invalidate_agency_complaint_cache(client: redis.Redis, agency_code: str) -> None:
    # Filters are baked into the key, so a single agency has many cached
    # variants (one per filter combination) -- clear them all on write.
    async for key in client.scan_iter(match=f"complaints:list:{agency_code}*"):
        await client.delete(key)