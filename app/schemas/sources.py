from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.base import ORMBaseModel
from app.services.crawl_config import DEFAULT_SOURCE_MAX_DAYS_OLD


SourceType = Literal["channel", "keyword", "playlist"]


class SourceCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "source_type": "channel",
                    "youtube_url": "link_youtube_url",
                    "max_days_old": DEFAULT_SOURCE_MAX_DAYS_OLD,
                }
            ]
        }
    )

    source_type: SourceType
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = None
    youtube_url: str | None = None
    max_days_old: int | None = Field(default=DEFAULT_SOURCE_MAX_DAYS_OLD, ge=1)

    @model_validator(mode="after")
    def require_identifier_or_channel_url(self) -> "SourceCreate":
        if self.identifier:
            return self
        if self.source_type == "channel" and self.youtube_url:
            return self
        raise ValueError("identifier is required unless channel source has youtube_url")


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
    subscriber_count: int | None = None
    view_count: int | None = None
    is_active: bool | None = None
    is_accessible: bool | None = None
    max_days_old: int | None = None
    created_at: datetime | None = None
    last_scraped: datetime | None = None
    next_scrape: datetime | None = None
    schedule_tier: int | None = None
    schedule_override_minutes: int | None = None
