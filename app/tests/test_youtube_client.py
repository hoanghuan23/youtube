from datetime import datetime

import pytest
from yt_dlp.utils import DownloadError

from app.services.youtube_client import YouTubeClient, YouTubeVideoItem


@pytest.mark.asyncio
async def test_keyword_client_is_offline_safe():
    client = YouTubeClient()

    videos = await client.get_keyword_videos("python", max_count=5)

    assert videos == []


@pytest.mark.asyncio
async def test_video_metrics_uses_extracted_video_info(monkeypatch):
    client = YouTubeClient()

    def fake_extract_video_info(_url):
        return YouTubeVideoItem(
            youtube_video_id="abc",
            youtube_url="https://www.youtube.com/watch?v=abc",
            metrics={"views_count": 10, "likes_count": 1, "comments_count": 0},
        )

    monkeypatch.setattr(client, "_extract_video_info", fake_extract_video_info)

    metrics = await client.get_video_metrics("https://www.youtube.com/watch?v=abc")

    assert metrics == {"views_count": 10, "likes_count": 1, "comments_count": 0}


def test_channel_videos_url_defaults_to_videos_and_preserves_explicit_tabs():
    assert YouTubeClient._channel_videos_url("vtv24") == "https://www.youtube.com/@vtv24/videos"
    assert YouTubeClient._channel_videos_url("@vtv24") == "https://www.youtube.com/@vtv24/videos"
    assert (
        YouTubeClient._channel_videos_url("https://www.youtube.com/@vtv24/videos")
        == "https://www.youtube.com/@vtv24/videos"
    )
    assert (
        YouTubeClient._channel_videos_url("https://www.youtube.com/@vtv24/shorts")
        == "https://www.youtube.com/@vtv24/shorts"
    )


def test_extract_video_info_maps_yt_dlp_video_data(monkeypatch):
    client = YouTubeClient()
    captured_opts = {}

    class FakeYoutubeDL:
        def __init__(self, opts):
            captured_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {
                "id": "YASe05eAlBI",
                "webpage_url": "https://www.youtube.com/shorts/YASe05eAlBI",
                "title": "Demo short",
                "description": "desc",
                "channel": "Demo Channel",
                "channel_id": "UC123",
                "channel_url": "https://www.youtube.com/@demo",
                "uploader": "Demo Uploader",
                "uploader_id": "@demo",
                "upload_date": "20260102",
                "duration": 12,
                "view_count": 1234,
                "like_count": 56,
                "comment_count": 7,
                "thumbnail": "https://img.youtube.com/demo.jpg",
                "tags": ["tag-a"],
                "categories": ["Music"],
            }

    monkeypatch.setattr(client, "_load_youtube_dl", lambda: FakeYoutubeDL)

    item = client._extract_video_info("https://www.youtube.com/shorts/YASe05eAlBI")

    assert captured_opts == {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "no_warnings": True,
    }
    assert item.youtube_video_id == "YASe05eAlBI"
    assert item.video_type == "short"
    assert item.published_at.year == 2026
    assert item.duration_seconds == 12
    assert item.thumbnail_url == "https://img.youtube.com/demo.jpg"
    assert item.channel == {
        "youtube_channel_id": "UC123",
        "channel_handle": "@demo",
        "channel_title": "Demo Channel",
        "channel_url": "https://www.youtube.com/@demo",
    }
    assert item.metrics == {"views_count": 1234, "likes_count": 56, "comments_count": 7}
    assert item.categories == '["Music"]'


def test_extract_channel_videos_stops_at_first_video_older_than_since(monkeypatch):
    client = YouTubeClient()
    calls = []

    class FakeYoutubeDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {
                "entries": [
                    {"id": "recent"},
                    {"id": "old"},
                    {"id": "after-old"},
                ]
            }

    published_at_by_id = {
        "recent": datetime(2026, 1, 10),
        "old": datetime(2026, 1, 1),
        "after-old": datetime(2026, 1, 11),
    }

    def fake_extract_video_info(video_url):
        video_id = video_url.rsplit("=", 1)[-1]
        calls.append(video_id)
        return YouTubeVideoItem(
            youtube_video_id=video_id,
            youtube_url=video_url,
            published_at=published_at_by_id[video_id],
        )

    monkeypatch.setattr(client, "_load_youtube_dl", lambda: FakeYoutubeDL)
    monkeypatch.setattr(client, "_extract_video_info", fake_extract_video_info)

    videos = client._extract_channel_videos(
        "https://www.youtube.com/@demo/videos",
        max_count=30,
        since=datetime(2026, 1, 5),
    )

    assert [video.youtube_video_id for video in videos] == ["recent"]
    assert calls == ["recent", "old"]


def test_extract_channel_videos_skips_unreleased_premiere(monkeypatch):
    client = YouTubeClient()

    class FakeYoutubeDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {
                "entries": [
                    {"id": "ready"},
                    {"id": "premiere"},
                    {"id": "after-premiere"},
                ]
            }

    def fake_extract_video_info(video_url):
        video_id = video_url.rsplit("=", 1)[-1]
        if video_id == "premiere":
            raise DownloadError("This live event will begin in a few moments. Premieres in 2 hours")
        return YouTubeVideoItem(
            youtube_video_id=video_id,
            youtube_url=video_url,
            published_at=datetime(2026, 1, 10),
        )

    monkeypatch.setattr(client, "_load_youtube_dl", lambda: FakeYoutubeDL)
    monkeypatch.setattr(client, "_extract_video_info", fake_extract_video_info)

    videos = client._extract_channel_videos(
        "https://www.youtube.com/@demo/videos",
        max_count=30,
        since=None,
    )

    assert [video.youtube_video_id for video in videos] == ["ready", "after-premiere"]


def test_extract_channel_videos_reports_antibot_issue(monkeypatch):
    issues = []
    client = YouTubeClient(issue_handler=issues.append)

    class FakeYoutubeDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return {"entries": [{"id": "protected"}]}

    def fake_extract_video_info(_video_url):
        raise DownloadError(
            "ERROR: secretstorage not available as the `secretstorage` module is not installed. "
            "Sign in to confirm you're not a bot."
        )

    monkeypatch.setattr(client, "_load_youtube_dl", lambda: FakeYoutubeDL)
    monkeypatch.setattr(client, "_extract_video_info", fake_extract_video_info)

    videos = client._extract_channel_videos("https://www.youtube.com/@demo/videos", max_count=30, since=None)

    assert videos == []
    assert len(issues) == 1
    assert issues[0].error_type == "YouTubeAntiBotError"
    assert issues[0].log_level == "WARNING"
    assert "protected" in issues[0].video_url
