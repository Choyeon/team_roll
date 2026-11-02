"""Authentication, admin account and session models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import AdminRole

USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    username: str
    display_name: str
    role: AdminRole
    capabilities: list[str]
    csrf_token: str
    expires_at: datetime
    last_login_at: datetime | None = None


class AdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: AdminRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    last_login_ip: str = ""
    failed_login_count: int = 0
    locked_until: datetime | None = None


class AdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(default="", max_length=80)
    role: AdminRole = AdminRole.ADMIN

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        import re

        if not re.match(USERNAME_PATTERN, value):
            raise ValueError("用户名需以字母或数字开头，仅允许字母、数字、下划线、点和连字符，长度 3-64")
        return value


class AdminUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=10, max_length=256)
    display_name: str | None = Field(default=None, max_length=80)
    role: AdminRole | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str
    user_agent: str
    revoked_at: datetime | None = None
    current: bool = False
