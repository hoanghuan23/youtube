import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import PipelineJob, PipelineLog, Source, TaskLog, Video, VideoMetric
from app.services.crawl_config import DEFAULT_SOURCE_MAX_DAYS_OLD
from app.services.tier_service import metric_tier_from_metric, next_metric_update_at, refresh_source_schedule, upsert_source_analytics_cache
from app.services.youtube_client import YouTubeClient, YouTubeExtractionIssue, YouTubeVideoItem, serialize_categories


logger = logging.getLogger("youtube_api.scraper")


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


def _latest_source_published_at(db: Session, source: Source) -> datetime | None:
    return db.query(func.max(Video.published_at)).filter(Video.source_id == source.id).scalar()


def _source_since(db: Session, source: Source) -> datetime:
    max_days_old = source.max_days_old if source.max_days_old is not None else DEFAULT_SOURCE_MAX_DAYS_OLD
    max_age_since = _now() - timedelta(days=max(max_days_old, 1))
    latest_published_at = _latest_source_published_at(db, source)
    if latest_published_at is None:
        return max_age_since
    latest_exclusive_since = latest_published_at.replace(tzinfo=None) + timedelta(microseconds=1)
    return max(max_age_since, latest_exclusive_since)


def _as_item(data: YouTubeVideoItem | dict[str, Any]) -> YouTubeVideoItem:
    if isinstance(data, YouTubeVideoItem):
        return data
    return YouTubeVideoItem(
        youtube_video_id=str(data.get("youtube_video_id") or data.get("video_id") or data.get("id")),
        youtube_url=str(data.get("youtube_url") or data.get("url")),
        title=data.get("title"),
        description=data.get("description"),
        published_at=data.get("published_at") or data.get("posted_at") or data.get("created_at_utc"),
        duration_seconds=_to_int(data.get("duration_seconds") or data.get("duration")),
        video_type=data.get("video_type") or "long",
        thumbnail_url=data.get("thumbnail_url") or data.get("thumbnail"),
        channel=data.get("channel"),
        metrics=data.get("metrics")
        or {
            "views_count": data.get("views_count") or data.get("view_count"),
            "likes_count": data.get("likes_count") or data.get("like_count"),
            "comments_count": data.get("comments_count") or data.get("comment_count"),
        },
        tags=data.get("tags"),
        categories=serialize_categories(data.get("categories")),
    )


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return _now()


def add_job_log(
    db: Session,
    job: PipelineJob,
    message: str,
    log_level: str = "ERROR",
    error_type: str | None = None,
    error_details: str | None = None,
) -> None:
    db.add(
        PipelineLog(
            job_id=job.id,
            source_id=job.source_id,
            log_level=log_level,
            message=message,
            error_type=error_type,
            error_details=error_details,
            created_at=_now(),
        )
    )


def add_task_log(db: Session, job: PipelineJob) -> None:
    completed_at = job.finished_at or _now()
    started_at = job.started_at or completed_at
    task_names = {
        "scrape_24h": "scrape_videos",
        "scraper_job": "scrape_videos",
        "update_metric": "update_metrics",
        "analytics": "generate_analytics",
    }
    db.add(
        TaskLog(
            task_name=task_names.get(job.job_type, job.job_type),
            status=job.status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=(completed_at - started_at).total_seconds(),
            items_processed=job.items_total,
            errors_count=job.items_failed,
            error_message=job.error_message,
            created_at=_now(),
        )
    )


def _create_job(db: Session, source: Source, job_type: str = "scraper_job") -> PipelineJob:
    job = PipelineJob(job_type=job_type, source_id=source.id, status="running", started_at=_now())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _video_to_metric(video: Video, item: YouTubeVideoItem, job_id: int, recorded_at: datetime) -> VideoMetric | None:
    metrics = item.metrics or {}
    if not metrics:
        return None
    return VideoMetric(
        video_id=video.id,
        views_count=_to_int(metrics.get("views_count")),
        likes_count=_to_int(metrics.get("likes_count")),
        comments_count=_to_int(metrics.get("comments_count")),
        recorded_at=recorded_at,
        job_id=job_id,
    )


def crawl_source_with_videos(
    db: Session,
    source: Source,
    videos: list[YouTubeVideoItem | dict[str, Any]],
    log_context: str = "crawl source",
    job: PipelineJob | None = None,
) -> PipelineJob:
    job = job or _create_job(db, source)
    items_total = 0
    videos_new = 0
    try:
        for raw_item in videos:
            item = _as_item(raw_item)
            items_total += 1
            if not item.youtube_video_id or not item.youtube_url:
                job.items_failed += 1
                continue
            if db.query(Video).filter(Video.youtube_video_id == item.youtube_video_id).first():
                continue

            video = Video(
                source_id=source.id,
                youtube_video_id=item.youtube_video_id,
                youtube_url=item.youtube_url,
                title=item.title,
                description=item.description,
                published_at=_coerce_datetime(item.published_at),
                duration_seconds=item.duration_seconds,
                video_type=item.video_type,
                thumbnail_url=item.thumbnail_url,
                categories=item.categories,
                created_at=_now(),
                is_tracked=True,
                is_deleted=False,
                metric_tier="bootstrap",
                cold_check_count=0,
                metric_scan_miss_count=0,
            )
            db.add(video)
            db.flush()
            recorded_at = _now()
            metric = _video_to_metric(video, item, job.id, recorded_at)
            if metric is not None:
                db.add(metric)
                db.flush()
                video.last_metric_update = recorded_at
                video.metric_tier = metric_tier_from_metric(metric)
                video.next_metric_update = next_metric_update_at(recorded_at, video.metric_tier)
            videos_new += 1

        job.videos_found = items_total
        job.videos_new = videos_new
        job.items_total = items_total
        job.items_updated = videos_new
        job.status = "done"
        job.finished_at = _now()
        source.last_scraped = job.finished_at
        upsert_source_analytics_cache(db, source, job.finished_at)
        refresh_source_schedule(db, source, job.finished_at)
        add_task_log(db, job)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.merge(job)
        job.status = "failed"
        job.error_message = str(exc)
        job.items_failed = max(job.items_failed, 1)
        job.finished_at = _now()
        add_job_log(db, job, "Crawl source failed", "ERROR", type(exc).__name__, str(exc))
        add_task_log(db, job)
        db.commit()
        logger.exception("YouTube source crawl failed")
    logger.info(
        "Hoan tat %s | source=%s id=%s job_id=%s status=%s found=%s new=%s failed=%s",
        log_context,
        _source_label(source),
        source.id,
        job.id,
        job.status,
        job.videos_found,
        job.videos_new,
        job.items_failed,
    )
    db.refresh(job)
    return job


async def crawl_source(db: Session, source: Source, max_count: int = 30) -> PipelineJob:
    job = _create_job(db, source)

    def add_youtube_issue_log(issue: YouTubeExtractionIssue) -> None:
        add_job_log(
            db,
            job,
            issue.message,
            issue.log_level,
            issue.error_type,
            issue.error_details,
        )
        job.items_failed += 1

    client = YouTubeClient(db, issue_handler=add_youtube_issue_log)
    logger.info(
        "Bat dau crawl video 72h cho source | source=%s id=%s type=%s max_count=%s",
        _source_label(source),
        source.id,
        source.source_type,
        max_count,
    )
    try:
        if source.source_type == "channel":
            videos = await client.get_channel_videos(
                source.youtube_url or source.identifier,
                max_count=max_count,
                since=_source_since(db, source),
            )
        elif source.source_type == "keyword":
            videos = await client.get_keyword_videos(source.identifier, max_count=max_count)
        elif source.source_type == "playlist":
            videos = await client.get_playlist_videos(source.identifier, max_count=max_count)
        else:
            job.status = "failed"
            job.error_message = f"Unsupported source_type={source.source_type}"
            job.finished_at = _now()
            db.commit()
            db.refresh(job)
            logger.info(
                "Hoan tat crawl video 72h cho source | source=%s id=%s job_id=%s status=%s found=%s new=%s failed=%s error=%s",
                _source_label(source),
                source.id,
                job.id,
                job.status,
                job.videos_found,
                job.videos_new,
                job.items_failed,
                job.error_message,
            )
            return job
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)
        job.items_failed = 1
        job.finished_at = _now()
        source.is_accessible = False
        source.last_scraped = job.finished_at
        add_job_log(db, job, "Fetch source videos failed", "ERROR", type(exc).__name__, str(exc))
        add_task_log(db, job)
        db.commit()
        db.refresh(job)
        logger.exception("Unable to fetch YouTube videos for source %s", source.id)
        logger.info(
            "Hoan tat crawl video 72h cho source | source=%s id=%s job_id=%s status=%s found=%s new=%s failed=%s error=%s",
            _source_label(source),
            source.id,
            job.id,
            job.status,
            job.videos_found,
            job.videos_new,
            job.items_failed,
            job.error_message,
        )
        return job
    return crawl_source_with_videos(db, source, videos, log_context="crawl video 72h cho source", job=job)
