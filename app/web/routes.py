"""HTML entry points: SPA shell per route with injected metadata, plus crawler files."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from app.core.config import Settings, get_settings
from app.core.deps import DbSession
from app.core.errors import NotFound
from app.web import seo, shell

router = APIRouter(include_in_schema=False)


def _base(request: Request, settings: Settings) -> str:
    return seo.base_url(settings, str(request.base_url))


@router.get("/")
async def home(request: Request, db: DbSession) -> Response:
    settings = get_settings()
    return shell.render(seo.home_meta(db, settings, _base(request, settings)), request, settings)


@router.get("/activity/{activity_id}")
async def activity_page(activity_id: str, request: Request, db: DbSession) -> Response:
    settings = get_settings()
    meta = seo.activity_meta(db, settings, _base(request, settings), activity_id)
    if meta is None:
        # The SPA renders the friendly "活动不存在" state; the shell still has to load.
        meta = seo.PageMeta(
            title=f"活动不存在 | {settings.app_name}",
            description="该 Roll 点活动不存在或已被删除。",
            canonical=f"{_base(request, settings)}/activity/{activity_id}",
            noindex=True,
        )
    return shell.render(meta, request, settings)


@router.get("/login")
async def login_page(request: Request) -> Response:
    settings = get_settings()
    return shell.render(seo.login_meta(settings, _base(request, settings)), request, settings)


@router.get("/admin")
@router.get("/admin/{section:path}")
async def admin_page(request: Request, section: str = "") -> Response:
    settings = get_settings()
    path = "/admin" + (f"/{section}" if section else "")
    return shell.render(seo.admin_meta(settings, _base(request, settings), path), request, settings)


@router.get("/robots.txt")
async def robots(request: Request) -> PlainTextResponse:
    settings = get_settings()
    return PlainTextResponse(seo.robots_txt(_base(request, settings)), media_type="text/plain; charset=utf-8")


@router.get("/sitemap.xml")
async def sitemap(request: Request, db: DbSession) -> Response:
    settings = get_settings()
    return Response(
        content=seo.sitemap_xml(db, _base(request, settings)),
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "max-age=300"},
    )


@router.get("/{full_path:path}")
async def spa_fallback(full_path: str, request: Request, db: DbSession) -> Response:
    """Client-side routes resolve to the shell; anything that looks like a file 404s."""
    if "." in full_path.rsplit("/", 1)[-1]:
        raise NotFound("资源不存在")
    settings = get_settings()
    meta = seo.home_meta(db, settings, _base(request, settings))
    # The SPA shows its own not-found view here, so keep the shell out of the index.
    meta.noindex = True
    return shell.render(meta, request, settings)
