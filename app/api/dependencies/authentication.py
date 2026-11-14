from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import extract_public_prefix
from app.db.dependencies import get_db_session
from app.schemas.principal import TenantPrincipal
from app.services.api_key_service import authenticate_api_key

bearer_scheme = HTTPBearer(auto_error=False, scheme_name="SentinelAPIKey")


async def require_tenant(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantPrincipal:
    cached_principal = getattr(request.state, "tenant_principal", None)
    if isinstance(cached_principal, TenantPrincipal):
        return cached_principal

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or inactive API key",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    presented_key = credentials.credentials
    public_prefix = extract_public_prefix(presented_key)
    if public_prefix is None:
        raise unauthorized

    authenticated = await authenticate_api_key(
        session,
        public_prefix=public_prefix,
        presented_key=presented_key,
    )
    if authenticated is None:
        raise unauthorized

    api_key, tenant = authenticated
    return TenantPrincipal(tenant_id=tenant.id, api_key_id=api_key.id)
