"""Shared schema primitives."""

from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PageInfo(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page_info: PageInfo
