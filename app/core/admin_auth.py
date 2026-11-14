import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_admin(
    supplied_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    configured_token = get_settings().admin_api_key
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrative API is not configured",
        )

    if supplied_token is None or not secrets.compare_digest(
        supplied_token, configured_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrative credentials",
        )
