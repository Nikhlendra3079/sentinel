from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import admin_auth


@pytest.mark.asyncio
async def test_admin_auth_rejects_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(admin_auth, "get_settings", lambda: SimpleNamespace(admin_api_key=None))

    with pytest.raises(HTTPException) as exc:
        await admin_auth.require_admin("anything")

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_admin_auth_rejects_wrong_token(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_auth,
        "get_settings",
        lambda: SimpleNamespace(admin_api_key="expected-secret"),
    )

    with pytest.raises(HTTPException) as exc:
        await admin_auth.require_admin("wrong-secret")

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_auth_accepts_correct_token(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_auth,
        "get_settings",
        lambda: SimpleNamespace(admin_api_key="expected-secret"),
    )

    assert await admin_auth.require_admin("expected-secret") is None
