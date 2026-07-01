from datetime import datetime

from app.models import Source, Video, VideoMetric
from app.services.scraper_service import crawl_source_with_videos
from app.services.youtube_client import YouTubeVideoItem


def test_crawl_source_with_videos_creates_video_metric_and_job(db_session):
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    item = YouTubeVideoItem(
        youtube_video_id="abc123",
        youtube_url="https://www.youtube.com/watch?v=abc123",
        title="Demo",
        description="#python video",
        published_at=datetime(2026, 1, 1, 12, 0, 0),
        metrics={"views_count": 100, "likes_count": 10, "comments_count": 2},
    )

    job = crawl_source_with_videos(db_session, source, [item])

    assert job.status == "done"
    assert job.videos_found == 1
    assert job.videos_new == 1
    assert db_session.query(Video).count() == 1
    assert db_session.query(VideoMetric).count() == 1
