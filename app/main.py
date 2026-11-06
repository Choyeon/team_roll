"""Application factory and wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import (
    activities,
    admin_accounts,
    admin_activities,
    admin_dashboard,
    admin_data,
    admin_rolls,
    auth,
    ws,
)
from app.core.config import Settings, get_settings
from app.core.deps import DbSession
from app.core.logging import RequestIdMiddleware, configure_logging
from app.core.security import client_ip, client_user_agent
from app.core.ws import ConnectionManager
from app.db import migrate
from app.db.session import get_engine, get_sessionmaker
from app.services import admins as admin_service
from app.web import routes as web_routes

logger = logging.getLogger("team_roll.app")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    engine = get_engine(settings)
    strategy = migrate.ensure_schema(settings, engine)

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    created = admin_service.bootstrap_admin(get_sessionmaker()(), settings)
    _log_startup_summary(settings, strategy, created)
    yield
    engine.dispose()


def _log_startup_summary(settings: Settings, strategy: str, bootstrapped) -> None:
    logger.info(
        "%s v%s 启动完成 env=%s db=%s schema=%s",
        settings.app_name,
        __version__,
        settings.environment,
        settings.database_url.split("///")[-1],
        strategy,
    )
    if settings.uses_default_secret and settings.is_production:
        logger.warning("生产环境仍在使用默认 SECRET_KEY，请设置一个随机密钥")
    if bootstrapped is not None:
        logger.warning("已从环境变量创建初始管理员 %s，请尽快登录并修改密码", bootstrapped.username)
    if not settings.trust_proxy_headers:
        logger.info("未启用代理头信任；如部署在 Nginx 之后请设置 TRUST_PROXY_HEADERS=true")


def _build_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.middleware("http")
    async def resolve_client_ip(request: Request, call_next):
        request.state.client_ip = client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
        request.state.user_agent = client_user_agent(request)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        headers = response.headers
        if request.url.path.startswith("/static/"):
            # Unhashed module filenames: revalidate so a deploy is picked up at once,
            # while StaticFiles' ETag still answers with 304.
            headers.setdefault("Cache-Control", "no-cache")
        # The shell sets its own, hash-aware CSP.
        if "content-security-policy" not in {key.lower() for key in headers}:
            headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if settings.is_production:
            headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=bool(settings.cors_allow_origins),
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "X-Requested-With"],
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.debug)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.ws_manager = ConnectionManager(max_per_activity=settings.ws_max_connections_per_activity)
    app.state.session_factory = get_sessionmaker()

    _build_middleware(app, settings)
    _register_exception_handlers(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(auth.router)
    api.include_router(activities.router)
    api.include_router(admin_dashboard.router)
    api.include_router(admin_activities.router)
    api.include_router(admin_rolls.router)
    api.include_router(admin_accounts.router)
    api.include_router(admin_data.router)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    async def healthz(db: DbSession) -> JSONResponse:
        try:
            db.execute(text("SELECT 1"))
            database_ok = True
        except Exception:  # pragma: no cover - only on a broken engine
            database_ok = False
        status_code = 200 if database_ok else 503
        return JSONResponse(
            {"status": "ok" if database_ok else "degraded", "version": __version__,
             "websocket_connections": app.state.ws_manager.total},
            status_code=status_code,
        )

    app.include_router(ws.router)
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
    # Registered last so /api, /static and /ws keep priority over the SPA catch-all.
    app.include_router(web_routes.router)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    from app.core.errors import register_exception_handlers

    register_exception_handlers(app)


app = create_app()
