"""Cross-cutting schema pieces."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta


class MessageOut(BaseModel):
    message: str


class ListParams(BaseModel):
    """Shared pagination/filter query parameters."""

    q: str = Field(default="", max_length=80)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def build_page(items: list, total: int, params: ListParams) -> dict:
    pages = (total + params.page_size - 1) // params.page_size if params.page_size else 0
    return {
        "items": items,
        "meta": {
            "page": params.page,
            "page_size": params.page_size,
            "total": total,
            "pages": pages,
        },
    }
