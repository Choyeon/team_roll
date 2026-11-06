"""Roll result request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import RollStatus


class RollSubmit(BaseModel):
    name: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _clean(self) -> RollSubmit:
        self.name = " ".join(self.name.split())
        if not self.name:
            raise ValueError("请输入你的名字")
        return self


class RollManualCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    number: int = Field(ge=0, le=1_000_000)
    reason: str = Field(default="", max_length=200)


class RollUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    number: int | None = Field(default=None, ge=0, le=1_000_000)
    reason: str = Field(default="", max_length=200)


class RollVoid(BaseModel):
    reason: str = Field(default="", max_length=200)


class RollPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    activity_id: str
    name: str
    number: int
    rank: int
    status: RollStatus
    timestamp: datetime


class RollAdminOut(RollPublic):
    ip: str = ""
    user_agent: str = ""
    void_reason: str = ""
    created_by: str = ""
