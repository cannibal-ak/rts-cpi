"""Shared schema primitives."""

from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PageInfo(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool

    # ── Additive fields; all defaulted so existing consumers are unaffected.
    # The grid endpoints refuse to run without a date filter and pin the newest
    # available date when the caller omits one. `applied_file_date` echoes which
    # date was actually used, so the UI can label the data it is showing instead
    # of guessing.
    applied_file_date: str | None = None
    # True when `total` was served from cache rather than recounted for this
    # request. Lets a client distinguish "genuinely zero rows" from "not counted".
    total_is_cached: bool = False


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page_info: PageInfo
