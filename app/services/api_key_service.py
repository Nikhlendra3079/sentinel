import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_api_key, verify_api_key
from app.models.api_key import ApiKey
from app.models.tenant import Tenant


class TenantNotFoundError(Exception):
    pass


class TenantInactiveError(Exception):
    pass


class ApiKeyNotFoundError(Exception):
    pass


async def issue_api_key(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantNotFoundError
    if tenant.status != "active":
        raise TenantInactiveError

    generated = generate_api_key()
    record = ApiKey(
        tenant_id=tenant_id,
        key_prefix=generated.public_prefix,
        key_hash=generated.key_hash,
        name=name,
        expires_at=expires_at,
    )
    session.add(record)
    await session.flush()
    return record, generated.full_key


async def revoke_api_key(session: AsyncSession, key_id: uuid.UUID) -> ApiKey:
    record = await session.get(ApiKey, key_id)
    if record is None:
        raise ApiKeyNotFoundError
    if record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        await session.flush()
    return record


async def rotate_api_key(
    session: AsyncSession,
    *,
    old_key_id: uuid.UUID,
    new_name: str | None = None,
) -> tuple[ApiKey, str]:
    # Lock the old credential row so two concurrent rotations cannot both
    # succeed against the same still-active key.
    old_record = await session.scalar(
        select(ApiKey).where(ApiKey.id == old_key_id).with_for_update()
    )
    if old_record is None:
        raise ApiKeyNotFoundError
    if old_record.revoked_at is not None:
        raise ApiKeyNotFoundError

    tenant = await session.get(Tenant, old_record.tenant_id)
    if tenant is None:
        raise TenantNotFoundError
    if tenant.status != "active":
        raise TenantInactiveError

    old_record.revoked_at = datetime.now(timezone.utc)
    new_record, plaintext_key = await issue_api_key(
        session,
        tenant_id=old_record.tenant_id,
        name=new_name or old_record.name,
        expires_at=old_record.expires_at,
    )
    await session.flush()
    return new_record, plaintext_key


async def authenticate_api_key(
    session: AsyncSession,
    *,
    public_prefix: str,
    presented_key: str,
) -> tuple[ApiKey, Tenant] | None:
    statement = (
        select(ApiKey)
        .where(ApiKey.key_prefix == public_prefix)
        .options(selectinload(ApiKey.tenant))
    )
    result = await session.execute(statement)
    record = result.scalar_one_or_none()
    if record is None:
        return None

    if not verify_api_key(presented_key, record.key_hash):
        return None
    if record.revoked_at is not None:
        return None
    if record.expires_at is not None and record.expires_at <= datetime.now(timezone.utc):
        return None
    if record.tenant.status != "active":
        return None

    return record, record.tenant
