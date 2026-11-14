"""Enforce one active policy per tenant and endpoint pattern.

Revision ID: 0003_active_policy_pattern
Revises: 0002_api_key_prefix
"""
from alembic import op

revision = "0003_active_policy_pattern"
down_revision = "0002_api_key_prefix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_active_policy_tenant_pattern",
        "rate_limit_policies",
        ["tenant_id", "endpoint_pattern"],
        unique=True,
        postgresql_where="is_active = true",
    )


def downgrade() -> None:
    op.drop_index("uq_active_policy_tenant_pattern", table_name="rate_limit_policies")
