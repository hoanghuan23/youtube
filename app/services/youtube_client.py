from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session


@dataclass(slots=True)
class YouTubeVideoItem:
    youtube_video_id: str
    youtube_url: str
    title: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    duration_text: str | None = None
    video_type: str = "long"
    thumbnail_url: str | None = None
    channel: dict[str, Any] | None = None
    metrics: dict[str, int | None] | None = None
    tags: list[str] | None = None


class YouTubeClient:
    """Offline-safe wrapper; real YouTube/yt-dlp calls can be added behind this interface."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    async def get_channel_videos(
        self,
        identifier: str,
        max_count: int = 30,
        since: datetime | None = None,
    ) -> list[YouTubeVideoItem]:
        return []

    async def get_keyword_videos(self, keyword: str, max_count: int = 30) -> list[YouTubeVideoItem]:
        return []

    async def get_playlist_videos(self, playlist_id: str, max_count: int = 30) -> list[YouTubeVideoItem]:
        return []

    async def get_video_metrics(self, youtube_url: str) -> dict[str, int | None]:
        return {"views_count": 0, "likes_count": 0, "comments_count": 0}

    async def get_video_info(self, youtube_url: str) -> YouTubeVideoItem:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        video_id = youtube_url.rstrip("/").split("/")[-1] or "unknown"
        if "watch?v=" in youtube_url:
            video_id = youtube_url.split("watch?v=", 1)[1].split("&", 1)[0]
        return YouTubeVideoItem(
            youtube_video_id=video_id,
            youtube_url=youtube_url,
            title=None,
            published_at=now,
            metrics=await self.get_video_metrics(youtube_url),
        )

    async def get_channel_info(self, channel_url: str) -> dict[str, Any] | None:
        return None
