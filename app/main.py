from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import engine
from app.routers import auth, complaints, attachments, ws, reports, health
from app.middleware import RateLimitMiddleware, RequestIDMiddleware, request_id_ctx
from app.core.deps import get_redis, require_scope
from app.logging_config import configure_logging, get_logger
from app.metrics import setup_instrumentator

configure_logging()
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # On shutdown: close the connection pool cleanly
    await engine.dispose()


app = FastAPI(title="NYC 311 Civic Data API", lifespan=lifespan)

instrumentator = setup_instrumentator(app)
instrumentator.expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
    dependencies=[Depends(require_scope("admin"))],
)

# Middleware runs bottom-up, so RequestIDMiddleware (added last) wraps every
# request first and RateLimitMiddleware can rely on the request ID already
# being set for logging.
app.add_middleware(
    RateLimitMiddleware,
    redis_client_getter=get_redis,
    authenticated_limit=200,
    unauthenticated_limit=30,
)
app.add_middleware(RequestIDMiddleware)

app.include_router(auth.router)
app.include_router(complaints.router)
app.include_router(attachments.router)
app.include_router(ws.router)
app.include_router(reports.router)
app.include_router(health.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "request_id": request_id_ctx.get(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/")
async def root():
    return {"status": "ok"}
