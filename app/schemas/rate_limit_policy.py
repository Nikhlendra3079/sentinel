import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AlgorithmName = Literal["token_bucket", "fixed_window", "sliding_window"]


class RateLimitPolicyCreate(BaseModel):
    algorithm: AlgorithmName
    limit_count: int = Field(gt=0)
    window_seconds: int = Field(gt=0)
    burst_capacity: int | None = Field(default=None, gt=0)
    endpoint_pattern: str = Field(default="*", min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_pattern(self):
        pattern = self.endpoint_pattern
        if pattern != "*" and (not pattern.startswith("/") or "*" in pattern[:-1] or ("*" in pattern and not pattern.endswith("/*"))):
            raise ValueError("endpoint_pattern must be '*', an exact path, or a path prefix ending in '/*'")
        return self


class RateLimitPolicyUpdate(BaseModel):
    algorithm: AlgorithmName | None = None
    limit_count: int | None = Field(default=None, gt=0)
    window_seconds: int | None = Field(default=None, gt=0)
    burst_capacity: int | None = Field(default=None, gt=0)
    endpoint_pattern: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_pattern(self):
        pattern = self.endpoint_pattern
        if pattern is not None and pattern != "*" and (not pattern.startswith("/") or "*" in pattern[:-1] or ("*" in pattern and not pattern.endswith("/*"))):
            raise ValueError("endpoint_pattern must be '*', an exact path, or a path prefix ending in '/*'")
        return self


class RateLimitPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    algorithm: AlgorithmName
    limit_count: int
    window_seconds: int
    burst_capacity: int | None
    endpoint_pattern: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
