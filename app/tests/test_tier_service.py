from datetime import datetime

from app.models import AnalyticsCache, Source, Video, VideoMetric
from app.services.tier_service import (
    calculate_source_schedule_tier,
    metric_tier_from_metric,
    next_metric_update_at,
    upsert_source_analytics_cache,
)


def test_metric_tier_and_next_update():
    metric = VideoMetric(views_count=10_000, likes_count=2_000, comments_count=200)

    tier = metric_tier_from_metric(metric)
    next_update = next_metric_update_at(datetime(2026, 1, 1, 0, 0, 0), tier)

    assert tier == "medium"
    assert next_update == datetime(2026, 1, 1, 4, 0, 0)


def test_upsert_source_analytics_cache_counts_latest_7_day_videos_and_updates_tier(db_session):
    now = datetime(2026, 1, 8, 12, 0, 0)
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=now)
    db_session.add(source)
    db_session.flush()
    db_session.add(
        AnalyticsCache(
            source_id=source.id,
            date=datetime(2026, 1, 7),
            avg_views_per_video=10_000,
            avg_likes_per_video=0,
            avg_comments_per_video=0,
        )
    )
    recent = Video(
        source_id=source.id,
        youtube_video_id="recent",
        youtube_url="https://www.youtube.com/watch?v=recent",
        published_at=datetime(2026, 1, 6, 12, 0, 0),
        metric_tier="bootstrap",
    )
    old = Video(
        source_id=source.id,
        youtube_video_id="old",
        youtube_url="https://www.youtube.com/watch?v=old",
        published_at=datetime(2025, 12, 31, 12, 0, 0),
        metric_tier="bootstrap",
    )
    db_session.add_all([recent, old])
    db_session.flush()
    db_session.add_all(
        [
            VideoMetric(video_id=recent.id, views_count=50_000, likes_count=100, comments_count=10, recorded_at=now),
            VideoMetric(video_id=old.id, views_count=1_000_000, likes_count=10_000, comments_count=1000, recorded_at=now),
        ]
    )
    db_session.flush()

    cache = upsert_source_analytics_cache(db_session, source, now)

    assert cache.date == datetime(2026, 1, 8)
    assert cache.total_videos == 1
    assert cache.total_views == 50_000
    assert cache.total_likes == 100
    assert cache.total_comments == 10
    assert cache.avg_views_per_video == 50_000
    assert cache.avg_likes_per_video == 100
    assert cache.avg_comments_per_video == 10
    assert cache.top_video_id == "recent"
    assert cache.growth_rate == 431.0
    assert source.schedule_tier == 5


def test_upsert_source_analytics_cache_updates_existing_daily_row(db_session):
    now = datetime(2026, 1, 8, 12, 0, 0)
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=now)
    db_session.add(source)
    db_session.flush()
    video = Video(
        source_id=source.id,
        youtube_video_id="abc123",
        youtube_url="https://www.youtube.com/watch?v=abc123",
        published_at=now,
        metric_tier="bootstrap",
    )
    db_session.add(video)
    db_session.flush()
    db_session.add(VideoMetric(video_id=video.id, views_count=1_000, likes_count=0, comments_count=0, recorded_at=now))
    db_session.flush()

    first = upsert_source_analytics_cache(db_session, source, now)
    db_session.flush()
    db_session.add(VideoMetric(video_id=video.id, views_count=2_000, likes_count=0, comments_count=0, recorded_at=now))
    db_session.flush()
    second = upsert_source_analytics_cache(db_session, source, now)

    assert second.id == first.id
    assert second.total_views == 2_000
    assert db_session.query(AnalyticsCache).filter(AnalyticsCache.source_id == source.id).count() == 1


def test_source_schedule_tier_thresholds():
    assert calculate_source_schedule_tier(100_000, 0) == 5
    assert calculate_source_schedule_tier(30_000, 0) == 4
    assert calculate_source_schedule_tier(8_000, 0) == 3
    assert calculate_source_schedule_tier(1_000, 0) == 2
    assert calculate_source_schedule_tier(999, 19) == 1
    assert calculate_source_schedule_tier(999, 20) == 3
