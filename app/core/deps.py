from dataclasses import dataclass
from datetime import datetime, timezone

import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import decode_access_token, hash_api_key, ROLE_SCOPES
from app.database import get_db
from app.models import ApiKey, PlatformUser

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class CurrentUser:
    user_id: str
    agency_code: str
    role: str
    scopes: list[str]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    api_key: str | None = Depends(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    # Try API key first if provided
    if api_key:
        key_hash = hash_api_key(api_key)
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        key_row = result.scalar_one_or_none()
        if key_row is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if key_row.expires_at and key_row.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API key expired")

        owner_result = await db.execute(select(PlatformUser).where(PlatformUser.id == key_row.owner_id))
        owner = owner_result.scalar_one_or_none()
        if owner is None:
            raise HTTPException(status_code=401, detail="API key owner not found")

        key_row.last_used_at = datetime.now(timezone.utc)
        await db.commit()

        return CurrentUser(
            user_id=str(owner.id),
            agency_code=owner.agency_code,
            role=owner.role,
            scopes=key_row.scopes,
        )

    # Fall back to JWT
    if credentials:
        try:
            payload = decode_access_token(credentials.credentials)
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return CurrentUser(
            user_id=payload["user_id"],
            agency_code=payload["agency_code"],
            role=payload["role"],
            scopes=ROLE_SCOPES.get(payload["role"], []),
        )

    raise HTTPException(status_code=401, detail="Not authenticated")


def require_scope(required_scope: str):
    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if required_scope not in user.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {required_scope}",
                headers={"WWW-Authenticate": f'Bearer scope="{required_scope}"'},
            )
        return user

    return _checker


_redis_pool: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_pool


async def get_arq_pool():
    return await create_pool(RedisSettings.from_dsn(get_settings().redis_url))