from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.base import ORMBaseModel


SourceType = Literal["channel", "keyword", "playlist"]


class SourceCreate(BaseModel):
    source_type: SourceType
    identifier: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    youtube_url: str | None = None
    max_days_old: int | None = Field(default=7, ge=1)


class SourceUpdate(BaseModel):
    display_name: str | None = None
    youtube_url: str | None = None
    is_active: bool | None = None
    is_accessible: bool | None = None
    max_days_old: int | None = Field(default=None, ge=1)
    schedule_tier: int | None = Field(default=None, ge=1, le=5)
    schedule_override_minutes: int | None = Field(default=None, ge=1)


class SourceRead(ORMBaseModel):
    id: int
    source_type: str
    identifier: str
    display_name: str | None = None
    youtube_url: str | None = None
    is_active: bool | None = None
    is_accessible: bool | None = None
    max_days_old: int | None = None
    created_at: datetime | None = None
    last_scraped: datetime | None = None
    next_scrape: datetime | None = None
    schedule_tier: int | None = None
    schedule_override_minutes: int | None = None
