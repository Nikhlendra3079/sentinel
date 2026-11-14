import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    tenant_id: uuid.UUID
    api_key_id: uuid.UUID
