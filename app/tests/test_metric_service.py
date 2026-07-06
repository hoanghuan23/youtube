from datetime import datetime

import pytest
from yt_dlp.utils import DownloadError

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
async def test_update_video_metric_skips_private_video(monkeypatch, db_session):
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.flush()
    video = Video(
        source_id=source.id,
        youtube_video_id="private123",
        youtube_url="https://www.youtube.com/watch?v=private123",
        published_at=datetime.utcnow(),
        metric_tier="bootstrap",
        is_tracked=True,
        is_deleted=False,
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)

    async def fake_fetch_metric(_video):
        raise DownloadError("Private video. Sign in if you've been granted access to this video.")

    monkeypatch.setattr(metric_service, "_fetch_metric", fake_fetch_metric)

    job = await metric_service.update_video_metric(db_session, video)

    assert job.status == "done"
    assert job.items_updated == 0
    assert job.items_failed == 0
    assert video.is_tracked is False
    assert video.is_deleted is True
    assert db_session.query(VideoMetric).count() == 0


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


@pytest.mark.asyncio
async def test_update_source_metrics_skips_private_video_and_continues(monkeypatch, db_session):
    now = datetime(2026, 1, 8, 12, 0, 0)
    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=now)
    db_session.add(source)
    db_session.flush()
    ready_video = Video(
        source_id=source.id,
        youtube_video_id="ready123",
        youtube_url="https://www.youtube.com/watch?v=ready123",
        published_at=now,
        metric_tier="bootstrap",
        is_tracked=True,
        is_deleted=False,
    )
    private_video = Video(
        source_id=source.id,
        youtube_video_id="private123",
        youtube_url="https://www.youtube.com/watch?v=private123",
        published_at=now,
        metric_tier="bootstrap",
        is_tracked=True,
        is_deleted=False,
    )
    db_session.add_all([ready_video, private_video])
    db_session.commit()
    db_session.refresh(ready_video)
    db_session.refresh(private_video)

    async def fake_fetch_metric(video):
        if video.youtube_video_id == "private123":
            raise DownloadError("Private video. Sign in if you've been granted access to this video.")
        return {"views_count": 1000, "likes_count": 0, "comments_count": 0}

    monkeypatch.setattr(metric_service, "_fetch_metric", fake_fetch_metric)

    job = await metric_service.update_source_metrics(db_session, source, videos=[ready_video, private_video], now=now)

    assert job.status == "done"
    assert job.items_updated == 1
    assert job.items_failed == 0
    assert ready_video.next_metric_update is not None
    assert private_video.is_tracked is False
    assert private_video.is_deleted is True
    assert db_session.query(VideoMetric).count() == 1
