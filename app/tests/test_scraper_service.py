import logging
from datetime import datetime, timedelta

from app.models import AnalyticsCache, Source, Video, VideoMetric
from app.services import scraper_service
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
        categories='["Music"]',
        published_at=datetime.utcnow(),
        metrics={"views_count": 50_000, "likes_count": 100, "comments_count": 10},
    )

    job = crawl_source_with_videos(db_session, source, [item])
    cache = db_session.query(AnalyticsCache).filter(AnalyticsCache.source_id == source.id).one()

    assert job.status == "done"
    assert job.videos_found == 1
    assert job.videos_new == 1
    assert db_session.query(Video).count() == 1
    assert db_session.query(VideoMetric).count() == 1
    assert db_session.query(Video).one().categories == '["Music"]'
    assert cache.total_videos == 1
    assert cache.total_views == 50_000
    assert cache.top_video_id == "abc123"
    assert source.schedule_tier == 3
    assert source.next_scrape is not None


def test_crawl_source_with_videos_serializes_dict_categories(db_session):
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    job = crawl_source_with_videos(
        db_session,
        source,
        [
            {
                "video_id": "dict123",
                "url": "https://www.youtube.com/watch?v=dict123",
                "title": "Dict demo",
                "categories": ["Education"],
                "published_at": datetime.utcnow(),
            }
        ],
    )

    assert job.status == "done"
    assert db_session.query(Video).one().categories == '["Education"]'


def test_crawl_source_with_videos_logs_custom_context(db_session, caplog):
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    with caplog.at_level(logging.INFO, logger="youtube_api.scraper"):
        crawl_source_with_videos(db_session, source, [], log_context="crawl video 72h cho source")

    assert "Hoan tat crawl video 72h cho source" in caplog.text
    assert "status=done" in caplog.text


def test_source_since_uses_latest_published_at_as_exclusive_boundary(db_session):
    source = Source(
        source_type="channel",
        identifier="demo",
        is_active=True,
        is_accessible=True,
        max_days_old=30,
        created_at=datetime.utcnow(),
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    latest_published_at = datetime.utcnow() - timedelta(hours=1)
    db_session.add(
        Video(
            source_id=source.id,
            youtube_video_id="existing",
            youtube_url="https://www.youtube.com/watch?v=existing",
            published_at=latest_published_at,
            created_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    assert scraper_service._source_since(db_session, source) == latest_published_at + timedelta(microseconds=1)
