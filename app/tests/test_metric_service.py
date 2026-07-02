from datetime import datetime

import pytest

from app.models import AnalyticsCache, Source, Video, VideoMetric
from app.services import metric_service


@pytest.mark.asyncio
async def test_update_video_metric_records_metric(monkeypatch, db_session):
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.flush()
    video = Video(
        source_id=source.id,
        youtube_video_id="abc123",
        youtube_url="https://www.youtube.com/watch?v=abc123",
        published_at=datetime.utcnow(),
        metric_tier="bootstrap",
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)

    async def fake_fetch_metric(_video):
        return {"views_count": 1000, "likes_count": 20, "comments_count": 3}

    monkeypatch.setattr(metric_service, "_fetch_metric", fake_fetch_metric)

    job = await metric_service.update_video_metric(db_session, video)

    assert job.status == "done"
    assert job.items_updated == 1
    assert db_session.query(VideoMetric).count() == 1
    assert video.next_metric_update is not None


@pytest.mark.asyncio
async def test_update_source_metrics_refreshes_analytics_and_source_tier(monkeypatch, db_session):
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
    db_session.commit()
    db_session.refresh(video)

    async def fake_fetch_metric(_video):
        return {"views_count": 10_000, "likes_count": 0, "comments_count": 0}

    monkeypatch.setattr(metric_service, "_fetch_metric", fake_fetch_metric)

    job = await metric_service.update_source_metrics(db_session, source, videos=[video], now=now)
    cache = db_session.query(AnalyticsCache).filter(AnalyticsCache.source_id == source.id).one()

    assert job.status == "done"
    assert job.items_updated == 1
    assert cache.total_videos == 1
    assert cache.total_views == 10_000
    assert source.schedule_tier == 2
    assert source.next_scrape is not None
