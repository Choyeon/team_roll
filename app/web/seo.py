"""Search-engine and generative-engine metadata for SPA routes.

The frontend is a client-rendered Vue app, so crawlers would otherwise see an
empty shell. Each entry URL is server-rendered with its own title, description,
Open Graph tags, canonical link and JSON-LD block, and the SPA hydrates over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Activity, ActivityStatus, RollResult, RollStatus

MAX_LEADERBOARD_ITEMS = 10
STATUS_LABEL = {
    ActivityStatus.ACTIVE: "进行中",
    ActivityStatus.PAUSED: "已暂停",
    ActivityStatus.ENDED: "已结束",
}


@dataclass
class PageMeta:
    title: str
    description: str
    canonical: str
    noindex: bool = False
    json_ld: list[dict] = field(default_factory=list)
    og_type: str = "website"


def base_url(settings: Settings, request_base: str) -> str:
    return settings.public_base_url or request_base.rstrip("/")


def _url(base: str, path: str) -> str:
    return f"{base}/{path.lstrip('/')}" if path else base


def home_meta(db: Session, settings: Settings, base: str) -> PageMeta:
    counts = db.execute(select(func.count(Activity.id))).scalar_one()
    active = db.execute(
        select(func.count(Activity.id)).where(Activity.status == ActivityStatus.ACTIVE)
    ).scalar_one()
    rolls = db.execute(select(func.count(RollResult.id))).scalar_one()

    description = (
        f"{settings.app_name} 是一个 MMO 队伍 Roll 点工具：管理员创建活动并设定数值区间，"
        f"队友在同一页面 Roll 点，结果按数值实时排行。当前开放 {active} 个活动，累计 {rolls} 条 Roll 记录。"
    )
    return PageMeta(
        title=f"{settings.app_name} - 团队 Roll 点工具",
        description=description,
        canonical=_url(base, ""),
        json_ld=[
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": settings.app_name,
                "url": _url(base, ""),
                "description": description,
                "inLanguage": "zh-CN",
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": f"{_url(base, '')}/?q={{search_term_string}}",
                    "query-input": "required name=search_term_string",
                },
            },
            {
                "@context": "https://schema.org",
                "@type": "Dataset",
                "name": f"{settings.app_name} Roll 点活动数据",
                "description": f"包含 {counts} 个 Roll 点活动、{rolls} 条 Roll 点记录。",
                "url": _url(base, ""),
                "creator": {"@type": "Organization", "name": settings.app_name},
            },
        ],
    )


def activity_meta(db: Session, settings: Settings, base: str, activity_id: str) -> PageMeta | None:
    activity = db.get(Activity, activity_id)
    if activity is None:
        return None

    top = list(
        db.execute(
            select(RollResult.name, RollResult.number)
            .where(RollResult.activity_id == activity.id, RollResult.status == RollStatus.VALID)
            .order_by(RollResult.number.desc())
            .limit(MAX_LEADERBOARD_ITEMS)
        ).all()
    )
    status_label = STATUS_LABEL.get(activity.status, "")
    total = db.execute(
        select(func.count(RollResult.id)).where(
            RollResult.activity_id == activity.id, RollResult.status == RollStatus.VALID
        )
    ).scalar_one()

    cap = f"，仅限前 {activity.max_participants} 人" if activity.max_participants else ""
    summary = (
        f"{activity.name}（{status_label}）：Roll 点范围 {activity.roll_min}-{activity.roll_max}，"
        f"每人最多 {activity.max_participations} 次{cap}，已有 {total} 条有效数值。"
    )
    if activity.description:
        summary = f"{activity.description[:120]} {summary}"

    page = _url(base, f"/activity/{activity.id}")
    leader_items = [
        {
            "@type": "ListItem",
            "position": index,
            "name": name,
            "description": f"Roll 点数值 {number}",
        }
        for index, (name, number) in enumerate(top, start=1)
    ]

    json_ld = [
        {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": activity.name,
            "description": summary,
            "url": page,
            "startDate": activity.created_at.isoformat(),
            "eventStatus": "https://schema.org/EventScheduled"
            if activity.status is ActivityStatus.ACTIVE
            else "https://schema.org/EventCancelled",
            "organizer": {"@type": "Organization", "name": settings.app_name},
            "offers": {"@type": "Offer", "price": "0", "availability": "https://schema.org/InStock"},
        }
    ]
    if leader_items:
        json_ld.append(
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "name": f"{activity.name} Roll 点排行",
                "itemListOrder": "https://schema.org/ItemListOrderDescending",
                "numberOfItems": total,
                "itemListElement": leader_items,
            }
        )

    return PageMeta(
        title=f"{activity.name} | {settings.app_name} Roll 点",
        description=summary,
        canonical=page,
        noindex=activity.status is ActivityStatus.PAUSED,
        json_ld=json_ld,
        og_type="article",
    )


def login_meta(settings: Settings, base: str) -> PageMeta:
    return PageMeta(
        title=f"管理员登录 | {settings.app_name}",
        description="管理员登录页面，仅面向活动组织者，不供搜索引擎收录。",
        canonical=_url(base, "/login"),
        noindex=True,
    )


def admin_meta(settings: Settings, base: str, path: str) -> PageMeta:
    return PageMeta(
        title=f"管理后台 | {settings.app_name}",
        description="活动与 Roll 记录管理后台，不供搜索引擎收录。",
        canonical=_url(base, path if path.startswith("/admin") else "/admin"),
        noindex=True,
    )


def sitemap_xml(db: Session, base: str) -> str:
    entries = [f"{_url(base, '')}/"]
    rows = db.execute(
        select(Activity.id, Activity.updated_at).order_by(Activity.created_at.desc()).limit(500)
    ).all()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url><loc>{loc}</loc><changefreq>hourly</changefreq><priority>0.8</priority></url>".format(
            loc=quote(entries[0], safe="/:")
        ),
    ]
    for activity_id, updated_at in rows:
        lines.append(
            "  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>minutely</changefreq>"
            "<priority>0.7</priority></url>".format(
                loc=quote(f"{_url(base, '')}/activity/{activity_id}", safe="/:"),
                lastmod=updated_at.date().isoformat(),
            )
        )
    lines.append("</urlset>")
    return "\n".join(lines)


def robots_txt(base: str) -> str:
    return "\n".join(
        [
            "User-agent: *",
            "Disallow: /admin",
            "Disallow: /login",
            "Disallow: /api/",
            "Allow: /",
            f"Sitemap: {_url(base, '')}/sitemap.xml",
            "",
        ]
    )
