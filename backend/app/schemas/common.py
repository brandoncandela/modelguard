from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserRef(ORM):
    id: int
    username: str
    full_name: str
    role: str
    title: str = ""


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str
    detail: Optional[str] = None
