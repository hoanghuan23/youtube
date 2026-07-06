from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from yt_dlp.utils import DownloadError

from sqlalchemy.orm import Session


logger = logging.getLogger("youtube_api.youtube_client")


@dataclass(slots=True)
class YouTubeExtractionIssue:
    video_url: str
    message: str
    log_level: str
    error_type: str
    error_details: str


@dataclass(slots=True)
class YouTubeVideoItem:
    youtube_video_id: str
    youtube_url: str
    title: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    duration_seconds: int | None = None
    video_type: str = "long"
    thumbnail_url: str | None = None
    channel: dict[str, Any] | None = None
    metrics: dict[str, int | None] | None = None
    tags: list[str] | None = None
    categories: str | None = None


def serialize_categories(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class YouTubeClient:
    """Small yt-dlp wrapper used by scraper jobs."""

    def __init__(
        self,
        db: Session | None = None,
        issue_handler: Callable[[YouTubeExtractionIssue], None] | None = None,
    ) -> None:
        self.db = db
        self.issue_handler = issue_handler

    async def get_channel_videos(
        self,
        identifier: str,
        max_count: int = 30,
        since: datetime | None = None,
    ) -> list[YouTubeVideoItem]:
        channel_url = self._channel_videos_url(identifier)
        return self._extract_channel_videos(channel_url, max_count=max_count, since=since)

    async def get_keyword_videos(self, keyword: str, max_count: int = 30) -> list[YouTubeVideoItem]:
        return []

    async def get_playlist_videos(self, playlist_id: str, max_count: int = 30) -> list[YouTubeVideoItem]:
        return []

    async def get_video_metrics(self, youtube_url: str) -> dict[str, int | None]:
        item = self._extract_video_info(youtube_url)
        return item.metrics or {"views_count": None, "likes_count": None, "comments_count": None}

    async def get_video_info(self, youtube_url: str) -> YouTubeVideoItem:
        return self._extract_video_info(youtube_url)

    async def get_channel_info(self, channel_url: str) -> dict[str, Any] | None:
        return None

    @staticmethod
    def _channel_videos_url(identifier: str) -> str:
        value = identifier.strip().rstrip("/")
        if value.startswith("http://") or value.startswith("https://"):
            if value.endswith("/shorts") or value.endswith("/videos"):
                return value
            return f"{value}/videos"
        if value.startswith("@") or value.startswith("UC"):
            return f"https://www.youtube.com/{value}/videos"
        return f"https://www.youtube.com/@{value}/videos"

    @staticmethod
    def _published_at(info: dict[str, Any]) -> datetime | None:
        timestamp = info.get("timestamp")
        if timestamp:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)

        upload_date = info.get("upload_date")
        if upload_date:
            try:
                return datetime.strptime(upload_date, "%Y%m%d")
            except ValueError:
                return None
        return None

    @staticmethod
    def _video_url(flat_item: dict[str, Any]) -> str | None:
        video_url = flat_item.get("url") or flat_item.get("webpage_url")
        video_id = flat_item.get("id")
        if video_url and not str(video_url).startswith("http"):
            return f"https://www.youtube.com/watch?v={video_url}"
        if not video_url and video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return video_url

    @staticmethod
    def _load_youtube_dl():
        from yt_dlp import YoutubeDL

        return YoutubeDL

    @staticmethod
    def _is_skippable_video_error(error: DownloadError) -> bool:
        msg = str(error).lower()
        return (
            "premieres in" in msg
            or "premiere" in msg
            or "private video" in msg
            or "video unavailable" in msg
            or "members-only" in msg
        )

    @staticmethod
    def _is_antibot_error(error: Exception) -> bool:
        msg = str(error).lower()
        return any(
            marker in msg
            for marker in (
                "sign in to confirm",
                "not a bot",
                "check bot",
                "anti-bot",
                "captcha",
                "too many requests",
                "http error 429",
                "rate limit",
                "secretstorage not available",
            )
        )

    def _report_extraction_issue(self, video_url: str, error: Exception) -> None:
        if not self.issue_handler:
            return
        is_antibot = self._is_antibot_error(error)
        self.issue_handler(
            YouTubeExtractionIssue(
                video_url=video_url,
                message=(
                    "YouTube anti-bot/check-bot detected while extracting video info"
                    if is_antibot
                    else "Error extracting YouTube video info"
                ),
                log_level="WARNING" if is_antibot else "ERROR",
                error_type="YouTubeAntiBotError" if is_antibot else type(error).__name__,
                error_details=f"url={video_url} error={error}",
            )
        )

    def _extract_raw_video_info(self, video_url: str) -> dict[str, Any]:
        YoutubeDL = self._load_youtube_dl()
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "no_warnings": True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_url, download=False) or {}

    def _extract_video_info(self, video_url: str) -> YouTubeVideoItem:
        info = self._extract_raw_video_info(video_url)
        channel_id = info.get("channel_id")
        channel_handle = info.get("uploader_id")
        channel = None
        if channel_id or info.get("channel") or info.get("channel_url"):
            channel = {
                "youtube_channel_id": channel_id,
                "channel_handle": channel_handle,
                "channel_title": info.get("channel") or info.get("uploader"),
                "channel_url": info.get("channel_url"),
            }

        return YouTubeVideoItem(
            youtube_video_id=str(info.get("id") or ""),
            youtube_url=info.get("webpage_url") or video_url,
            title=info.get("title"),
            description=info.get("description"),
            published_at=self._published_at(info),
            duration_seconds=info.get("duration"),
            video_type="short" if "/shorts/" in (info.get("webpage_url") or video_url) else "long",
            thumbnail_url=info.get("thumbnail"),
            channel=channel,
            metrics={
                "views_count": info.get("view_count"),
                "likes_count": info.get("like_count"),
                "comments_count": info.get("comment_count"),
            },
            tags=info.get("tags") or info.get("categories"),
            categories=serialize_categories(info.get("categories")),
        )

    def _extract_channel_videos(
        self,
        channel_videos_url: str,
        max_count: int,
        since: datetime | None,
    ) -> list[YouTubeVideoItem]:
        YoutubeDL = self._load_youtube_dl()
        playlist_opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": max_count,
            "ignoreerrors": True,
            "no_warnings": True,
        }
        with YoutubeDL(playlist_opts) as ydl:
            playlist_info = ydl.extract_info(channel_videos_url, download=False)

        entries = (playlist_info or {}).get("entries") or []
        if not entries:
            logger.warning(
                "No YouTube channel videos extracted | url=%s title=%s",
                channel_videos_url,
                (playlist_info or {}).get("title"),
            )
        videos: list[YouTubeVideoItem] = []
        since_naive = since.replace(tzinfo=None) if since and since.tzinfo else since

        for flat_item in entries[:max_count]:
            if not flat_item:
                continue
            video_url = self._video_url(flat_item)
            if not video_url:
                continue
            try:
                item = self._extract_video_info(video_url)
            except DownloadError as e:
                if self._is_skippable_video_error(e):
                    logger.warning("Skip unavailable YouTube video | url=%s error=%s", video_url, e)
                    continue
                logger.warning("Error extracting YouTube video info | url=%s error=%s", video_url, e)
                self._report_extraction_issue(video_url, e)
                continue

            if since_naive and item.published_at and item.published_at < since_naive:
                break
            if channel_videos_url.endswith("/shorts") and item.video_type == "long":
                item.video_type = "short"
            videos.append(item)
        return videos
