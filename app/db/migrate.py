"""Schema bootstrap helpers used at application start."""

from __future__ import annotations

import logging

from sqlalchemy import Engine, inspect

from app.core.config import PROJECT_ROOT, Settings
from app.db.base import Base

logger = logging.getLogger("team_roll.db")

ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

# The pre-2.0 tables that revision 0001 describes.
LEGACY_TABLES = {"activities", "roll_results", "admin_sessions"}


def missing_tables(engine: Engine) -> set[str]:
    existing = set(inspect(engine).get_table_names())
    return set(Base.metadata.tables) - existing


def _alembic_config(settings: Settings):
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def upgrade_head(settings: Settings) -> None:
    from alembic import command

    command.upgrade(_alembic_config(settings), "head")


def ensure_schema(settings: Settings, engine: Engine) -> str:
    """Bring the database up to head, stamping 1.x databases before migrating them."""
    if not ALEMBIC_INI.is_file():
        logger.warning("未找到 alembic.ini，退化为 create_all 建表")
        Base.metadata.create_all(engine)
        return "create_all"

    from alembic import command

    config = _alembic_config(settings)
    existing = set(inspect(engine).get_table_names())

    if "alembic_version" not in existing:
        if not settings.database_auto_migrate:
            raise RuntimeError("数据库尚未纳入版本管理；请执行 `alembic upgrade head` 或开启 DATABASE_AUTO_MIGRATE")
        if existing & LEGACY_TABLES:
            logger.info("检测到 1.x 数据库，基线标记为 0001 后继续迁移")
            command.stamp(config, "0001")

    if settings.database_auto_migrate:
        command.upgrade(config, "head")
    elif missing_tables(engine):
        raise RuntimeError(
            f"数据库缺少表 {sorted(missing_tables(engine))}，且 DATABASE_AUTO_MIGRATE=false；请执行 `alembic upgrade head`"
        )
    return "alembic"
