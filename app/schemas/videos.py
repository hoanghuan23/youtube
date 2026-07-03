from datetime import datetime

from app.schemas.base import ORMBaseModel


class VideoMetricRead(ORMBaseModel):
    id: int
    video_id: int
    views_count: int | None = None
    likes_count: int | None = None
    comments_count: int | None = None
    recorded_at: datetime | None = None
    job_id: int | None = None


class VideoRead(ORMBaseModel):
    id: int
    source_id: int
    youtube_video_id: str
    youtube_url: str
    title: str | None = None
    description: str | None = None
    categories: str | None = None
    published_at: datetime
    duration_seconds: int | None = None
    video_type: str | None = None
    thumbnail_url: str | None = None
    is_tracked: bool | None = None
    is_deleted: bool | None = None
    last_metric_update: datetime | None = None
    next_metric_update: datetime | None = None
    metric_tier: str
