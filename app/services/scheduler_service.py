import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import SessionLocal
from app.models import Source, Video
from app.services.metric_service import update_source_metrics
from app.services.scraper_service import crawl_source


SUPPORTED_SOURCE_TYPES = ("channel", "keyword", "playlist")
logger = logging.getLogger("youtube_api.scheduler")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _source_label(source: Source | None) -> str:
    if source is None:
        return "unknown"
    return source.display_name or source.identifier or source.youtube_url or f"source-{source.id}"


def due_sources(db: Session, now: datetime, limit: int | None = None) -> list[Source]:
    query = (
        db.query(Source)
        .filter(Source.source_type.in_(SUPPORTED_SOURCE_TYPES))
        .filter(Source.is_active.is_(True))
        .filter(or_(Source.is_accessible.is_(True), Source.is_accessible.is_(None)))
        .filter(or_(Source.next_scrape.is_(None), Source.next_scrape <= now))
        .order_by(Source.next_scrape.is_not(None), Source.next_scrape.asc(), Source.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def due_videos(db: Session, now: datetime, limit: int | None = None) -> list[Video]:
    query = (
        db.query(Video)
        .filter(Video.published_at > now - timedelta(hours=24))
        .filter(or_(Video.is_tracked.is_(True), Video.is_tracked.is_(None)))
        .filter(or_(Video.is_deleted.is_(False), Video.is_deleted.is_(None)))
        .filter(or_(Video.next_metric_update.is_(None), Video.next_metric_update <= now))
        .order_by(Video.next_metric_update.is_not(None), Video.next_metric_update.asc(), Video.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def expire_old_tracked_videos(db: Session, now: datetime) -> int:
    expired_count = (
        db.query(Video)
        .filter(Video.published_at <= now - timedelta(hours=24))
        .filter(or_(Video.is_tracked.is_(True), Video.is_tracked.is_(None)))
        .filter(or_(Video.is_deleted.is_(False), Video.is_deleted.is_(None)))
        .update({Video.is_tracked: False}, synchronize_session=False)
    )
    db.commit()
    return expired_count


async def run_scheduler_cycle(
    db: Session,
    now: datetime | None = None,
    source_limit: int | None = None,
    video_limit: int | None = None,
    max_count: int = 30,
) -> dict[str, Any]:
    settings = get_settings()
    current_time = now or _now()
    source_batch_size = source_limit if source_limit is not None else settings.scheduler_source_batch_size
    video_batch_size = video_limit if video_limit is not None else settings.scheduler_video_batch_size
    videos_expired = expire_old_tracked_videos(db, current_time)

    source_job_ids = []
    source_jobs_failed = 0
    due_source_batch = due_sources(db, current_time, source_batch_size)
    if due_source_batch:
        logger.info("Scheduler bat dau crawl sources | sources=%s max_count=%s", len(due_source_batch), max_count)
    for source in due_source_batch:
        logger.info(
            "Scheduler chay crawl source | source=%s id=%s type=%s",
            _source_label(source),
            source.id,
            source.source_type,
        )
        job = await crawl_source(db, source, max_count=max_count)
        source_job_ids.append(job.id)
        if getattr(job, "status", None) == "failed":
            source_jobs_failed += 1

    metric_job_ids = []
    metric_jobs_failed = 0
    videos_by_source: dict[int, list[Video]] = defaultdict(list)
    due_video_batch = due_videos(db, current_time, video_batch_size)
    for video in due_video_batch:
        videos_by_source[video.source_id].append(video)
    if videos_by_source:
        logger.info(
            "Scheduler bat dau cap nhat metrics | sources=%s posts=%s",
            len(videos_by_source),
            len(due_video_batch),
        )
    for source_id, source_videos in videos_by_source.items():
        source = db.get(Source, source_id)
        if source is None:
            continue
        logger.info(
            "Scheduler chay metrics source | source=%s id=%s posts=%s",
            _source_label(source),
            source.id,
            len(source_videos),
        )
        job = await update_source_metrics(db, source, videos=source_videos, now=current_time)
        metric_job_ids.append(job.id)
        if getattr(job, "status", None) == "failed":
            metric_jobs_failed += 1

    logger.info(
        "Scheduler hoan tat chu ky | sources_processed=%s posts_processed=%s posts_expired=%s source_failed=%s metric_failed=%s",
        len(source_job_ids),
        len(due_video_batch),
        videos_expired,
        source_jobs_failed,
        metric_jobs_failed,
    )

    return {
        "sources_processed": len(source_job_ids),
        "videos_processed": len(due_video_batch),
        "videos_expired": videos_expired,
        "source_job_ids": source_job_ids,
        "metric_job_ids": metric_job_ids,
        "source_jobs_failed": source_jobs_failed,
        "metric_jobs_failed": metric_jobs_failed,
    }


async def run_scheduler_forever() -> None:
    settings = get_settings()
    logger.info("Scheduler started | interval_seconds=%s", settings.scheduler_interval_seconds)
    while True:
        await asyncio.sleep(settings.scheduler_interval_seconds)
        db = SessionLocal()
        try:
            await run_scheduler_cycle(db)
        except Exception:
            logger.exception("Scheduler cycle failed")
        finally:
            db.close()
