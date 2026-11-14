import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RateLimitPolicy(Base):
    __tablename__ = "rate_limit_policies"
    __table_args__ = (
        CheckConstraint("algorithm IN ('token_bucket', 'fixed_window', 'sliding_window')",
                        name="ck_policy_algorithm"),
        CheckConstraint("limit_count > 0", name="ck_policy_limit_count_positive"),
        CheckConstraint("window_seconds > 0", name="ck_policy_window_seconds_positive"),
        CheckConstraint("burst_capacity IS NULL OR burst_capacity > 0",
                        name="ck_policy_burst_capacity_positive"),
        CheckConstraint("version > 0", name="ck_policy_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    limit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    burst_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    endpoint_pattern: Mapped[str] = mapped_column(String(255), nullable=False, default="*")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="policies")
