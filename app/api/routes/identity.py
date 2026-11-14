from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.authentication import require_tenant
from app.db.dependencies import get_db_session
from app.models.tenant import Tenant
from app.schemas.principal import TenantPrincipal
from app.schemas.tenant import TenantRead

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.get("/me", response_model=TenantRead)
async def get_authenticated_tenant(
    principal: Annotated[TenantPrincipal, Depends(require_tenant)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Tenant:
    tenant = await session.get(Tenant, principal.tenant_id)
    # The tenant could have been deleted between authentication and this lookup.
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant is no longer available",
        )
    return tenant


@router.get("/protected/ping")
async def protected_ping(
    principal: Annotated[TenantPrincipal, Depends(require_tenant)],
) -> dict[str, str]:
    return {"message": "Authenticated request accepted", "tenant_id": str(principal.tenant_id)}
