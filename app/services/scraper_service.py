import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Channel, PipelineJob, PipelineLog, Source, TaskLog, Video, VideoMetric
from app.services.tier_service import metric_tier_from_metric, next_metric_update_at, refresh_source_schedule
from app.services.youtube_client import YouTubeClient, YouTubeVideoItem


logger = logging.getLogger("youtube_api.scraper")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_since(source: Source) -> datetime:
    max_days_old = source.max_days_old if source.max_days_old is not None else 1
    return _now() - timedelta(days=max(max_days_old, 1))


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
        duration_text=data.get("duration_text"),
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


def _upsert_channel(db: Session, item: YouTubeVideoItem) -> Channel | None:
    channel_data = item.channel or {}
    youtube_channel_id = channel_data.get("youtube_channel_id") or channel_data.get("channel_id")
    if not youtube_channel_id:
        return None
    channel = db.query(Channel).filter(Channel.youtube_channel_id == youtube_channel_id).first()
    if channel is None:
        channel = Channel(youtube_channel_id=youtube_channel_id, created_at=_now())
        db.add(channel)
    channel.channel_handle = channel_data.get("channel_handle") or channel_data.get("handle")
    channel.channel_title = channel_data.get("channel_title") or channel_data.get("title") or channel_data.get("channel_name")
    channel.channel_url = channel_data.get("channel_url") or channel_data.get("url")
    channel.thumbnail_url = channel_data.get("thumbnail_url")
    channel.subscriber_count = _to_int(channel_data.get("subscriber_count"))
    channel.video_count = _to_int(channel_data.get("video_count"))
    channel.view_count = _to_int(channel_data.get("view_count"))
    channel.description = channel_data.get("description")
    channel.last_updated = _now()
    db.flush()
    return channel


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


def crawl_source_with_videos(db: Session, source: Source, videos: list[YouTubeVideoItem | dict[str, Any]]) -> PipelineJob:
    job = _create_job(db, source)
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

            channel = _upsert_channel(db, item)
            video = Video(
                source_id=source.id,
                channel_id=channel.id if channel else None,
                youtube_video_id=item.youtube_video_id,
                youtube_url=item.youtube_url,
                title=item.title,
                description=item.description,
                published_at=_coerce_datetime(item.published_at),
                duration_seconds=item.duration_seconds,
                duration_text=item.duration_text,
                video_type=item.video_type,
                thumbnail_url=item.thumbnail_url,
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
    db.refresh(job)
    return job


async def crawl_source(db: Session, source: Source, max_count: int = 30) -> PipelineJob:
    client = YouTubeClient(db)
    try:
        if source.source_type == "channel":
            videos = await client.get_channel_videos(source.youtube_url or source.identifier, max_count=max_count, since=_source_since(source))
        elif source.source_type == "keyword":
            videos = await client.get_keyword_videos(source.identifier, max_count=max_count)
        elif source.source_type == "playlist":
            videos = await client.get_playlist_videos(source.identifier, max_count=max_count)
        else:
            job = _create_job(db, source)
            job.status = "failed"
            job.error_message = f"Unsupported source_type={source.source_type}"
            job.finished_at = _now()
            db.commit()
            db.refresh(job)
            return job
    except Exception as exc:
        job = _create_job(db, source)
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
        return job
    return crawl_source_with_videos(db, source, videos)
