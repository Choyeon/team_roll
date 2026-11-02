"""Dashboard, audit and system introspection models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrendPoint(BaseModel):
    day: date
    rolls: int


class TopActivity(BaseModel):
    id: str
    name: str
    status: str
    roll_count: int
    top_number: int | None = None
    completion: float = 0.0


class KpiSet(BaseModel):
    activities_total: int
    activities_active: int
    activities_ended: int
    rolls_total: int
    rolls_valid: int
    rolls_void: int
    participants_unique: int
    rolls_today: int
    rolls_last_7_days: int
    avg_fill_rate: float = 0.0
    median_fill_rate: float = 0.0


class DashboardOut(BaseModel):
    generated_at: datetime
    kpis: KpiSet
    trend: list[TrendPoint]
    top_activities: list[TopActivity]
    status_breakdown: list[dict[str, Any]]
    live_connections: int = 0
    recent_rolls: list[dict[str, Any]] = Field(default_factory=list)
    recent_audit: list[dict[str, Any]] = Field(default_factory=list)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor_label: str
    target_type: str
    target_id: str
    detail: str
    ip: str
    created_at: datetime


class DatabaseInfo(BaseModel):
    url_scheme: str
    file_size_bytes: int
    tables: dict[str, int]


class SystemOut(BaseModel):
    app_name: str
    version: str
    environment: str
    debug: bool
    python_version: str
    server_time: datetime
    uptime_seconds: float
    websocket_connections: int
    session_ttl_minutes: int
    rate_limits: dict[str, int]
    database: DatabaseInfo
