from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_scope
from app.core.security import generate_api_key, hash_password, verify_password, create_access_token
from app.database import get_db
from app.models import ApiKey, PlatformUser
from app.schemas.auth import ApiKeyCreate, TokenResponse, UserLogin, UserRegister, UserRoleUpdate

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    # 1. check if email already exists -> 409 if so
    existing = await db.execute(select(PlatformUser).where(PlatformUser.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # 2. hash the password
    hashed = hash_password(payload.password)

    # 3. create + add + commit + refresh the PlatformUser
    user = PlatformUser(
        email=payload.email,
        hashed_password=hashed,
        full_name=payload.full_name,
        agency_code=payload.agency_code.upper(),
        role="staff",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # 4. create_access_token(...) and return it
    token = create_access_token(user_id=str(user.id), agency_code=user.agency_code, role=user.role)
    return TokenResponse(access_token=token)

@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    # 1. query PlatformUser by email
    result = await db.execute(select(PlatformUser).where(PlatformUser.email == payload.email))
    user = result.scalar_one_or_none()

    # 2. if not found or verify_password fails -> 401
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # 3. create_access_token(...) and return it
    token = create_access_token(user_id=str(user.id), agency_code=user.agency_code, role=user.role)
    return TokenResponse(access_token=token)


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: UUID,
    payload: UserRoleUpdate,
    admin: CurrentUser = Depends(require_scope("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = payload.role
    await db.commit()
    return {"id": str(target.id), "email": target.email, "role": target.role}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    payload: ApiKeyCreate,
    user: CurrentUser = Depends(require_scope("admin")),
    db: AsyncSession = Depends(get_db),
):
    raw_key, key_prefix, key_hash = generate_api_key()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days
        else None
    )

    key_row = ApiKey(
        key_prefix=key_prefix,
        key_hash=key_hash,
        owner_id=user.user_id,
        scopes=payload.scopes,
        expires_at=expires_at,
    )
    db.add(key_row)
    await db.commit()

    return {
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "scopes": payload.scopes,
        "expires_at": expires_at,
        "note": "Save this key now -- it cannot be retrieved again.",
    }


@router.get("/api-keys")
async def list_api_keys(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ApiKey).where(ApiKey.owner_id == user.user_id))
    keys = result.scalars().all()
    return [
        {
            "id": str(k.id),
            "key_prefix": k.key_prefix,
            "scopes": k.scopes,
            "expires_at": k.expires_at,
            "last_used_at": k.last_used_at,
        }
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.owner_id == user.user_id)
    )
    key_row = result.scalar_one_or_none()
    if key_row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(key_row)
    await db.commit()

