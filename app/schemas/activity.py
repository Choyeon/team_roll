"""Activity request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import ActivityStatus


class ActivityInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    roll_min: int = Field(default=1, ge=0, le=1_000_000)
    roll_max: int = Field(default=100, ge=1, le=1_000_000)
    max_participations: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def _check_range(self) -> ActivityInput:
        if self.roll_max < self.roll_min:
            raise ValueError("Roll 点最大值必须不小于最小值")
        return self

    @model_validator(mode="after")
    def _normalise(self) -> ActivityInput:
        self.name = self.name.strip()
        self.description = self.description.strip()
        if not self.name:
            raise ValueError("活动名称不能为空")
        return self


class ActivityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    roll_min: int | None = Field(default=None, ge=0, le=1_000_000)
    roll_max: int | None = Field(default=None, ge=1, le=1_000_000)
    max_participations: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def _strip(self) -> ActivityUpdate:
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("活动名称不能为空")
        return self


class ActivityStatusUpdate(BaseModel):
    status: ActivityStatus


class ActivityPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    status: ActivityStatus
    roll_min: int
    roll_max: int
    max_participations: int
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None

    roll_count: int = 0
    participants: int = 0
    remaining_numbers: int = 0
    top_number: int | None = None


class ActivityAdminOut(ActivityPublic):
    updated_at: datetime
    created_by: str = ""
    void_count: int = 0
