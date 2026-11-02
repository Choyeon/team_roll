"""Render the SPA shell with per-route metadata and a matching CSP header."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from html import escape
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.config import Settings
from app.web.seo import PageMeta

SLOT = "<!--seo-slot-->"

_shell_cache: dict[str, tuple[float, str]] = {}

# Vue's global build compiles the in-file templates at runtime, which needs
# 'unsafe-eval'. Everything else stays strict, and the JSON-LD block is hash-based
# so no untrusted inline script can slip through.
CSP_TEMPLATE = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-eval'{script_hash}; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'{connect}; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)


class ShellUnavailable(RuntimeError):
    pass


def _shell_template(path: Path) -> str:
    stat_mtime = path.stat().st_mtime if path.is_file() else 0.0
    cached = _shell_cache.get(str(path))
    if cached and cached[0] == stat_mtime:
        return cached[1]
    if not path.is_file():
        raise ShellUnavailable(f"缺少前端入口文件 {path}")
    text = path.read_text(encoding="utf-8")
    _shell_cache[str(path)] = (stat_mtime, text)
    return text


def _json_ld_script(blocks: list[dict]) -> str:
    if not blocks:
        return ""
    payload = json.dumps(blocks if len(blocks) > 1 else blocks[0], ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    return f'<script type="application/ld+json">{payload}</script>'


def _head_fragment(meta: PageMeta, settings: Settings) -> str:
    tags = [
        f"<title>{escape(meta.title)}</title>",
        f'<meta name="description" content="{escape(meta.description)}">',
        f'<link rel="canonical" href="{escape(meta.canonical)}">',
        f'<meta property="og:title" content="{escape(meta.title)}">',
        f'<meta property="og:description" content="{escape(meta.description)}">',
        f'<meta property="og:type" content="{escape(meta.og_type)}">',
        f'<meta property="og:url" content="{escape(meta.canonical)}">',
        f'<meta property="og:site_name" content="{escape(settings.app_name)}">',
        '<meta name="twitter:card" content="summary">',
        '<meta name="twitter:title" content="' + escape(meta.title) + '">',
        '<meta name="twitter:description" content="' + escape(meta.description) + '">',
        '<meta name="theme-color" content="#4f46e5" media="(prefers-color-scheme: dark)">',
    ]
    if meta.noindex:
        tags.append('<meta name="robots" content="noindex,nofollow">')
    else:
        tags.append('<meta name="robots" content="index,follow,max-image-preview:large">')
    return "\n    ".join(tags)


def _safe_host(value: str) -> str:
    """Only echo a well-formed ``host:port`` into the CSP header."""
    return value if re.fullmatch(r"[A-Za-z0-9.\-_]{1,253}(:\d{1,5})?", value) else ""


def render(meta: PageMeta, request: Request, settings: Settings) -> HTMLResponse:
    template = _shell_template(settings.spa_shell)
    script = _json_ld_script(meta.json_ld)
    head = _head_fragment(meta, settings) + ("\n    " + script if script else "")
    html = template.replace(SLOT, head)

    script_hash = ""
    if script:
        body = script[script.index(">") + 1 : script.rindex("<")]
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        script_hash = f" 'sha256-{digest}'"

    scheme = "wss" if request.url.scheme == "https" else "ws"
    host = _safe_host(request.headers.get("host", ""))
    connect = f" {scheme}://{host}" if host else ""
    csp = CSP_TEMPLATE.format(script_hash=script_hash, connect=connect)

    return HTMLResponse(
        content=html,
        headers={
            "Content-Security-Policy": csp,
            "X-Robots-Tag": "noindex" if meta.noindex else "index",
            "Cache-Control": "no-cache",
            "Vary": "Accept-Encoding",
        },
    )
