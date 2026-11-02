"""Typed application settings, loaded once from environment + ``.env``."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

Environment = Literal["dev", "prod", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Team Roll"
    environment: Environment = "dev"
    debug: bool = False

    # --- security ---
    secret_key: SecretStr = SecretStr("dev-only-insecure-secret-change-me")
    bootstrap_admin_username: str = Field(
        default="admin", validation_alias=AliasChoices("BOOTSTRAP_ADMIN_USERNAME", "ADMIN_USERNAME")
    )
    bootstrap_admin_password: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("BOOTSTRAP_ADMIN_PASSWORD", "ADMIN_PASSWORD")
    )
    session_ttl_minutes: int = Field(default=120, ge=1, le=24 * 60)
    cookie_name: str = "session_id"
    csrf_cookie_name: str = "csrf_token"
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    max_failed_logins: int = Field(default=8, ge=1)
    lockout_minutes: int = Field(default=15, ge=1)
    trust_proxy_headers: bool = False
    # NoDecode: the value is a plain comma-separated list, not JSON.
    cors_allow_origins: Annotated[list[str], NoDecode] = []

    # --- rate limits: "requests/window_seconds" ---
    login_rate_limit: int = Field(default=10, ge=1)
    login_rate_window_seconds: int = Field(default=60, ge=1)
    roll_rate_limit: int = Field(default=12, ge=1)
    roll_rate_window_seconds: int = Field(default=60, ge=1)

    # --- database ---
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'team_roll.db'}"
    sql_echo: bool = False
    database_auto_migrate: bool = True
    # Pre-2.0 rows were written with naive ``datetime.now()``; revision 0005 rewinds
    # them to real UTC using this offset from the old server's local clock.
    legacy_local_offset_minutes: int = Field(default=480, ge=-14 * 60, le=14 * 60)

    # --- roll rules ---
    roll_min_value: int = Field(default=1, ge=0)
    roll_max_value: int = Field(default=10_000, ge=2)
    activity_name_max_length: int = Field(default=80, ge=1, le=200)
    participant_name_max_length: int = Field(default=32, ge=1, le=64)
    description_max_length: int = Field(default=2000, ge=1, le=20_000)

    # --- http ---
    host: str = "0.0.0.0"
    port: int = Field(default=8803, ge=1, le=65535)
    public_base_url: str = ""
    ws_heartbeat_seconds: int = Field(default=30, ge=5, le=600)
    ws_max_connections_per_activity: int = Field(default=500, ge=1)

    # --- storage layout ---
    static_dir: Path = PROJECT_ROOT / "static"
    spa_shell: Path = PROJECT_ROOT / "static" / "index.html"

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _reject_async_driver(cls, value: str) -> str:
        # The application is synchronous SQL; an aiosqlite URL silently breaks sessions.
        return value.replace("+aiosqlite", "")

    @model_validator(mode="after")
    def _apply_environment_defaults(self) -> Settings:
        if self.cookie_secure is None:
            # Only a production deployment is assumed to terminate TLS.
            object.__setattr__(self, "cookie_secure", self.environment == "prod")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("cookie_samesite='none' requires cookie_secure=true")
        if self.public_base_url.endswith("/"):
            object.__setattr__(self, "public_base_url", self.public_base_url.rstrip("/"))
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    @property
    def session_ttl(self) -> timedelta:
        return timedelta(minutes=self.session_ttl_minutes)

    @property
    def lockout_duration(self) -> timedelta:
        return timedelta(minutes=self.lockout_minutes)

    @property
    def uses_default_secret(self) -> bool:
        return self.secret_key.get_secret_value() == "dev-only-insecure-secret-change-me"

    @property
    def bootstrap_password_is_configured(self) -> bool:
        return self.bootstrap_admin_password is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
