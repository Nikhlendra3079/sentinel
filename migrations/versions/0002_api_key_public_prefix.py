"""Add public API-key lookup prefix.

Revision ID: 0002_api_key_prefix
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_api_key_prefix"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("key_prefix", sa.String(length=16), nullable=True))
    # Existing keys predate the new key format. Mark them revoked and give them
    # unique non-authenticating prefixes before enforcing NOT NULL + uniqueness.
    op.execute(
        "UPDATE api_keys SET key_prefix = left(md5(id::text), 16), "
        "revoked_at = COALESCE(revoked_at, now()) WHERE key_prefix IS NULL"
    )
    op.alter_column("api_keys", "key_prefix", nullable=False)
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_column("api_keys", "key_prefix")
