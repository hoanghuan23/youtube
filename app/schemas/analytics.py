from datetime import datetime

from app.schemas.base import ORMBaseModel


class AnalyticsCacheRead(ORMBaseModel):
    id: int
    source_id: int
    date: datetime
    total_videos: int | None = None
    total_views: int | None = None
    total_likes: int | None = None
    total_comments: int | None = None
    avg_views_per_video: float | None = None
    avg_likes_per_video: float | None = None
    avg_comments_per_video: float | None = None
    top_video_id: str | None = None
    growth_rate: float | None = None
    cached_at: datetime | None = None
