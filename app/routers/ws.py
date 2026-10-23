import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.deps import get_redis
from app.metrics import active_ws_connections

router = APIRouter(tags=["websocket"])

PUSH_INTERVAL_SECONDS = 3


@router.websocket("/ws/live")
async def live_stats(websocket: WebSocket):
    await websocket.accept()
    active_ws_connections.inc()
    redis_client = get_redis()

    try:
        while True:
            stats_raw = await redis_client.get("boroughs:stats")
            stats = json.loads(stats_raw) if stats_raw else []

            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "by_borough": stats,
            }
            await websocket.send_json(payload)
            await asyncio.sleep(PUSH_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    finally:
        active_ws_connections.dec()