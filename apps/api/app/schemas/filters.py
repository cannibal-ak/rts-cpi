"""Filter metadata schemas."""

from pydantic import BaseModel


class FilterMetadataOut(BaseModel):
    field: str
    label: str
    values: list[str]
