import pytest

from app.services.youtube_client import YouTubeClient


@pytest.mark.asyncio
async def test_stub_client_is_offline_safe():
    client = YouTubeClient()

    videos = await client.get_keyword_videos("python", max_count=5)
    metrics = await client.get_video_metrics("https://www.youtube.com/watch?v=abc")

    assert videos == []
    assert metrics == {"views_count": 0, "likes_count": 0, "comments_count": 0}
