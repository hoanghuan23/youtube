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
