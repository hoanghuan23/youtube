import pytest

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
