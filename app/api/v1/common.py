"""Shared API helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from app.schemas.common import ListParams, build_page


def list_params(
    q: str = Query(default="", max_length=80, description="按名称/描述/ID 模糊匹配"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> ListParams:
    return ListParams(q=q.strip(), page=page, page_size=page_size)


ListQuery = Annotated[ListParams, Depends(list_params)]


def page(items: list, total: int, params: ListParams) -> dict:
    return build_page(items, total, params)


def connection_manager(request: Request):
    return request.app.state.ws_manager
