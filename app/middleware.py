import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client_getter, authenticated_limit: int, unauthenticated_limit: int):
        super().__init__(app)
        self._get_redis = redis_client_getter
        self.authenticated_limit = authenticated_limit
        self.unauthenticated_limit = unauthenticated_limit

    def _client_identity(self, request: Request) -> tuple[str, bool]:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            return f"jwt:{auth_header}", True

        forwarded_for = request.headers.get("X-Forwarded-For")
        client_ip = (
            forwarded_for.split(",")[0].strip()
            if forwarded_for
            else (request.client.host if request.client else "unknown")
        )
        return f"ip:{client_ip}", False

    async def dispatch(self, request: Request, call_next):
        client_id, is_authenticated = self._client_identity(request)
        limit = self.authenticated_limit if is_authenticated else self.unauthenticated_limit
        redis_client = self._get_redis()

        now = time.time()
        window_start = now - WINDOW_SECONDS
        key = f"ratelimit:{client_id}"

        await redis_client.zremrangebyscore(key, 0, window_start)
        current_count = await redis_client.zcard(key)

        if current_count >= limit:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after_seconds": WINDOW_SECONDS},
                headers={
                    "Retry-After": str(WINDOW_SECONDS),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        await redis_client.zadd(key, {str(now): now})
        await redis_client.expire(key, WINDOW_SECONDS)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count - 1))
        return response
