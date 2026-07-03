import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PipelineJob, Source, Video, VideoMetric
from app.services.scraper_service import add_job_log, add_task_log
from app.services.tier_service import metric_tier_from_metric, next_metric_update_at, refresh_source_schedule, upsert_source_analytics_cache
from app.services.youtube_client import YouTubeClient


logger = logging.getLogger("youtube_api.metrics")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _source_label(source: Source | None) -> str:
    if source is None:
        return "unknown"
    return source.display_name or source.identifier or source.youtube_url or f"source-{source.id}"


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def due_videos_for_source(db: Session, source_id: int, now: datetime) -> list[Video]:
    return (
        db.query(Video)
        .filter(Video.source_id == source_id)
        .filter(Video.published_at > now - timedelta(hours=24))
        .filter(or_(Video.is_tracked.is_(True), Video.is_tracked.is_(None)))
        .filter(or_(Video.is_deleted.is_(False), Video.is_deleted.is_(None)))
        .filter(or_(Video.next_metric_update.is_(None), Video.next_metric_update <= now))
        .order_by(Video.next_metric_update.is_not(None), Video.next_metric_update.asc(), Video.id.asc())
        .all()
    )


def _create_metric_job(db: Session, source: Source | None, items_total: int = 1) -> PipelineJob:
    job = PipelineJob(
        job_type="update_metric",
        source_id=source.id if source else None,
        status="running",
        items_total=items_total,
        started_at=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


async def _fetch_metric(video: Video) -> dict[str, int | None]:
    settings = get_settings()
    client = YouTubeClient()
    if settings.metric_request_delay_seconds > 0:
        await asyncio.sleep(0)
    return await client.get_video_metrics(video.youtube_url)


def _record_metric(db: Session, video: Video, metrics: dict[str, Any], job: PipelineJob, recorded_at: datetime) -> None:
    metric = VideoMetric(
        video_id=video.id,
        views_count=_to_int(metrics.get("views_count")),
        likes_count=_to_int(metrics.get("likes_count")),
        comments_count=_to_int(metrics.get("comments_count")),
        recorded_at=recorded_at,
        job_id=job.id,
    )
    db.add(metric)
    db.flush()
    video.last_metric_update = recorded_at
    video.metric_tier = metric_tier_from_metric(metric)
    video.next_metric_update = next_metric_update_at(recorded_at, video.metric_tier)
    video.metric_scan_miss_count = 0


async def update_video_metric(db: Session, video: Video) -> PipelineJob:
    source = db.get(Source, video.source_id)
    job = _create_metric_job(db, source)
    logger.info(
        "Bat dau cap nhat metric | source=%s id=%s video_id=%s job_id=%s",
        _source_label(source),
        source.id if source else None,
        video.id,
        job.id,
    )
    try:
        metrics = await _fetch_metric(video)
        _record_metric(db, video, metrics, job, _now())
        job.items_updated = 1
        job.status = "done"
        job.finished_at = _now()
        add_task_log(db, job)
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.items_failed = 1
        job.finished_at = _now()
        add_job_log(db, job, "Metric update failed", "ERROR", type(exc).__name__, str(exc))
        add_task_log(db, job)
        db.commit()
    logger.info(
        "Hoan tat cap nhat metric | source=%s id=%s video_id=%s job_id=%s status=%s updated=%s failed=%s",
        _source_label(source),
        source.id if source else None,
        video.id,
        job.id,
        job.status,
        job.items_updated,
        job.items_failed,
    )
    db.refresh(job)
    return job


async def update_source_metrics(
    db: Session,
    source: Source,
    videos: list[Video] | None = None,
    now: datetime | None = None,
) -> PipelineJob:
    current_time = now or _now()
    videos = videos if videos is not None else due_videos_for_source(db, source.id, current_time)
    job = _create_metric_job(db, source, items_total=len(videos))
    logger.info(
        "Bat dau cap nhat metrics | source=%s id=%s posts=%s job_id=%s",
        _source_label(source),
        source.id,
        len(videos),
        job.id,
    )
    try:
        for video in videos:
            metrics = await _fetch_metric(video)
            _record_metric(db, video, metrics, job, current_time)
            job.items_updated += 1
        upsert_source_analytics_cache(db, source, current_time)
        refresh_source_schedule(db, source, current_time)
        job.status = "done"
        job.finished_at = _now()
        add_task_log(db, job)
        db.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.items_failed = max(job.items_failed, 1)
        job.finished_at = _now()
        add_job_log(db, job, "Source metric update failed", "ERROR", type(exc).__name__, str(exc))
        add_task_log(db, job)
        db.commit()
    logger.info(
        "Hoan tat cap nhat metrics | source=%s id=%s job_id=%s status=%s updated=%s failed=%s",
        _source_label(source),
        source.id,
        job.id,
        job.status,
        job.items_updated,
        job.items_failed,
    )
    db.refresh(job)
    return job
