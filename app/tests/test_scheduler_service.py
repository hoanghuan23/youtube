from datetime import datetime, timedelta

import pytest

from app.models import Source, Video, VideoMetric
from app.services import scheduler_service


@pytest.mark.asyncio
async def test_scheduler_picks_due_source(monkeypatch, db_session):
    source = Source(source_type="keyword", identifier="python", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.commit()

    async def fake_crawl_source(_db, _source, max_count=30):
        class Job:
            id = 99

        return Job()

    monkeypatch.setattr(scheduler_service, "crawl_source", fake_crawl_source)

    result = await scheduler_service.run_scheduler_cycle(db_session, now=datetime.utcnow(), source_limit=10, video_limit=10)

    assert result["sources_processed"] == 1
    assert result["source_job_ids"] == [99]


@pytest.mark.asyncio
async def test_scheduler_updates_due_video_metrics(monkeypatch, db_session):
    now = datetime(2026, 1, 8, 12, 0, 0)
    source = Source(
        source_type="channel",
        identifier="demo",
        is_active=True,
        is_accessible=True,
        created_at=now,
        next_scrape=now + timedelta(hours=1),
    )
    db_session.add(source)
    db_session.flush()

    due_video = Video(
        source_id=source.id,
        youtube_video_id="due123",
        youtube_url="https://www.youtube.com/watch?v=due123",
        published_at=now - timedelta(hours=1),
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="bootstrap",
        is_tracked=True,
        is_deleted=False,
    )
    future_video = Video(
        source_id=source.id,
        youtube_video_id="future123",
        youtube_url="https://www.youtube.com/watch?v=future123",
        published_at=now - timedelta(hours=1),
        next_metric_update=now + timedelta(minutes=30),
        metric_tier="bootstrap",
        is_tracked=True,
        is_deleted=False,
    )
    old_video = Video(
        source_id=source.id,
        youtube_video_id="old123",
        youtube_url="https://www.youtube.com/watch?v=old123",
        published_at=now - timedelta(days=2),
        next_metric_update=now - timedelta(minutes=1),
        metric_tier="bootstrap",
        is_tracked=True,
        is_deleted=False,
    )
    db_session.add_all([due_video, future_video, old_video])
    db_session.commit()

    async def fake_fetch_metric(video):
        assert video.youtube_video_id == "due123"
        return {"views_count": 5_000, "likes_count": 0, "comments_count": 0}

    import app.services.metric_service as metric_service

    monkeypatch.setattr(metric_service, "_fetch_metric", fake_fetch_metric)

    result = await scheduler_service.run_scheduler_cycle(db_session, now=now, source_limit=10, video_limit=10)

    db_session.refresh(due_video)
    db_session.refresh(future_video)
    db_session.refresh(old_video)
    metrics = db_session.query(VideoMetric).all()

    assert result["sources_processed"] == 0
    assert result["videos_processed"] == 1
    assert result["videos_expired"] == 1
    assert len(result["metric_job_ids"]) == 1
    assert len(metrics) == 1
    assert metrics[0].video_id == due_video.id
    assert due_video.last_metric_update == now
    assert due_video.metric_tier == "low"
    assert due_video.next_metric_update == now + timedelta(hours=6)
    assert future_video.last_metric_update is None
    assert old_video.is_tracked is False
