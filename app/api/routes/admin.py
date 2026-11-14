import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import require_admin
from app.db.dependencies import get_db_session
from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.models.rate_limit_policy import RateLimitPolicy
from app.schemas.api_key import ApiKeyCreate, ApiKeyIssued, ApiKeyRead
from app.schemas.tenant import TenantCreate, TenantRead, TenantStatusUpdate
from app.schemas.rate_limit_policy import (
    RateLimitPolicyCreate, RateLimitPolicyRead, RateLimitPolicyUpdate,
)
from app.services.api_key_service import (
    ApiKeyNotFoundError,
    TenantInactiveError,
    TenantNotFoundError,
    issue_api_key,
    revoke_api_key,
    rotate_api_key,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["administration"],
    dependencies=[Depends(require_admin)],
)


@router.post("/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    session: AsyncSession = Depends(get_db_session),
) -> Tenant:
    tenant = Tenant(name=payload.name.strip(), status="active")
    if not tenant.name:
        raise HTTPException(status_code=422, detail="Tenant name cannot be blank")
    session.add(tenant)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Tenant name already exists") from exc
    await session.refresh(tenant)
    return tenant


@router.get("/tenants/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.patch("/tenants/{tenant_id}/status", response_model=TenantRead)
async def update_tenant_status(
    tenant_id: uuid.UUID,
    payload: TenantStatusUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.status = payload.status
    await session.commit()
    await session.refresh(tenant)
    return tenant


@router.post(
    "/tenants/{tenant_id}/keys",
    response_model=ApiKeyIssued,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    tenant_id: uuid.UUID,
    payload: ApiKeyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyIssued:
    try:
        record, plaintext_key = await issue_api_key(
            session,
            tenant_id=tenant_id,
            name=payload.name,
            expires_at=payload.expires_at,
        )
        await session.commit()
        await session.refresh(record)
    except TenantNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Tenant not found") from exc
    except TenantInactiveError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Tenant is not active") from exc
    except Exception:
        await session.rollback()
        raise
    return ApiKeyIssued(key=plaintext_key, record=record)


@router.get("/tenants/{tenant_id}/keys", response_model=list[ApiKeyRead])
async def list_api_keys(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[ApiKey]:
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    result = await session.scalars(
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.all())


@router.post("/keys/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKey:
    try:
        record = await revoke_api_key(session, key_id)
        await session.commit()
        await session.refresh(record)
        return record
    except ApiKeyNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail="API key not found") from exc


@router.post(
    "/keys/{key_id}/rotate",
    response_model=ApiKeyIssued,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_key(
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyIssued:
    try:
        new_record, plaintext_key = await rotate_api_key(
            session, old_key_id=key_id
        )
        await session.commit()
        await session.refresh(new_record)
    except ApiKeyNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Active API key not found") from exc
    except TenantNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Tenant not found") from exc
    except TenantInactiveError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Tenant is not active") from exc
    return ApiKeyIssued(key=plaintext_key, record=new_record)


@router.post(
    "/tenants/{tenant_id}/policies",
    response_model=RateLimitPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_rate_limit_policy(
    tenant_id: uuid.UUID,
    payload: RateLimitPolicyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> RateLimitPolicy:
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    existing = await session.scalar(
        select(RateLimitPolicy.id).where(
            RateLimitPolicy.tenant_id == tenant_id,
            RateLimitPolicy.endpoint_pattern == payload.endpoint_pattern,
            RateLimitPolicy.is_active.is_(True),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="An active policy already uses this endpoint pattern")
    policy = RateLimitPolicy(tenant_id=tenant_id, **payload.model_dump())
    session.add(policy)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="An active policy already uses this endpoint pattern") from exc
    await session.refresh(policy)
    return policy


@router.get("/tenants/{tenant_id}/policies", response_model=list[RateLimitPolicyRead])
async def list_rate_limit_policies(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[RateLimitPolicy]:
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    result = await session.scalars(
        select(RateLimitPolicy)
        .where(RateLimitPolicy.tenant_id == tenant_id)
        .order_by(RateLimitPolicy.created_at.desc())
    )
    return list(result.all())


@router.patch("/policies/{policy_id}", response_model=RateLimitPolicyRead)
async def update_rate_limit_policy(
    policy_id: uuid.UUID,
    payload: RateLimitPolicyUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> RateLimitPolicy:
    policy = await session.get(RateLimitPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Rate-limit policy not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return policy
    target_pattern = changes.get("endpoint_pattern", policy.endpoint_pattern)
    target_active = changes.get("is_active", policy.is_active)
    if target_active:
        duplicate = await session.scalar(
            select(RateLimitPolicy.id).where(
                RateLimitPolicy.tenant_id == policy.tenant_id,
                RateLimitPolicy.endpoint_pattern == target_pattern,
                RateLimitPolicy.is_active.is_(True),
                RateLimitPolicy.id != policy.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="An active policy already uses this endpoint pattern")
    for field, value in changes.items():
        setattr(policy, field, value)
    policy.version += 1
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="An active policy already uses this endpoint pattern") from exc
    await session.refresh(policy)
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_limit_policy(
    policy_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    policy = await session.get(RateLimitPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Rate-limit policy not found")
    await session.delete(policy)
    await session.commit()
