from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import AnalyticsCache, Source, Video, VideoMetric


VIDEO_TIER_THRESHOLDS = (
    (100_000, "viral"),
    (30_000, "high"),
    (8_000, "medium"),
    (1_000, "low"),
)

METRIC_UPDATE_INTERVAL_MINUTES = {
    "bootstrap": 60,
    "viral": 120,
    "high": 180,
    "medium": 240,
    "low": 360,
    "very_low": 720,
}

BASE_INTERVAL_MINUTES = {
    "channel":120,
    "keyword":180,
    "playlist": 360,
}

TIER_MULTIPLIER = {5: 0.75, 4: 1, 3: 1.5, 2: 2.5, 1: 4}

SOURCE_TIER_THRESHOLDS = (
    (100_000, 100, 5),
    (30_000, 50, 4),
    (8_000, 20, 3),
    (1_000, None, 2),
)


def _value(value: int | float | None) -> int | float:
    return value or 0


def calculate_video_metric_score(
    views: int | None = 0,
    likes: int | None = 0,
    comments: int | None = 0,
) -> float:
    score = _value(views) * 0.2 + _value(likes) * 5 + _value(comments) * 12
    return round(float(score), 2)


def calculate_source_score(
    avg_views_per_video: float | None = 0,
    avg_likes_per_video: float | None = 0,
    avg_comments_per_video: float | None = 0,
) -> float:
    return calculate_video_metric_score(
        views=avg_views_per_video,
        likes=avg_likes_per_video,
        comments=avg_comments_per_video,
    )


def calculate_video_metric_tier(score: float) -> str:
    for threshold, tier in VIDEO_TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "very_low"


def calculate_source_schedule_tier(source_score: float, growth_rate: float | None = 0) -> int:
    growth = float(growth_rate or 0)
    for score_threshold, growth_threshold, tier in SOURCE_TIER_THRESHOLDS:
        if source_score >= score_threshold or (growth_threshold is not None and growth >= growth_threshold):
            return tier
    return 1


def metric_tier_from_metric(metric: VideoMetric) -> str:
    score = calculate_video_metric_score(
        views=metric.views_count,
        likes=metric.likes_count,
        comments=metric.comments_count,
    )
    return calculate_video_metric_tier(score)


def next_metric_update_at(recorded_at: datetime, metric_tier: str) -> datetime:
    minutes = METRIC_UPDATE_INTERVAL_MINUTES.get(
        metric_tier,
        METRIC_UPDATE_INTERVAL_MINUTES["medium"],
    )
    return recorded_at + timedelta(minutes=minutes)


def calculate_next_scrape_interval(
    source_type: str,
    schedule_tier: int | None,
    total_active_sources: int,
    schedule_override_minutes: int | None = None,
) -> timedelta:
    if schedule_override_minutes is not None:
        return timedelta(minutes=schedule_override_minutes)
    tier = schedule_tier or 1
    load_multiplier = 1 if total_active_sources <= 50 else 1.5
    minutes = int(BASE_INTERVAL_MINUTES.get(source_type, 120) * TIER_MULTIPLIER.get(tier, 1) * load_multiplier)
    return timedelta(minutes=max(15, min(360, minutes)))


def refresh_source_schedule(db: Session, source: Source, now: datetime) -> None:
    total_active_sources = db.query(Source).filter(Source.is_active.is_(True)).count()
    source.next_scrape = now + calculate_next_scrape_interval(
        source.source_type,
        source.schedule_tier,
        total_active_sources,
        source.schedule_override_minutes,
    )


def upsert_source_analytics_cache(db: Session, source: Source, now: datetime) -> AnalyticsCache:
    date = datetime(now.year, now.month, now.day)
    since = now - timedelta(days=7)
    videos = (
        db.query(Video)
        .filter(Video.source_id == source.id)
        .filter(Video.published_at >= since)
        .filter(or_(Video.is_tracked.is_(True), Video.is_tracked.is_(None)))
        .filter(or_(Video.is_deleted.is_(False), Video.is_deleted.is_(None)))
        .all()
    )
    totals = {"views": 0, "likes": 0, "comments": 0}
    top_video_id = None
    top_score = -1.0
    for video in videos:
        metric = (
            db.query(VideoMetric)
            .filter(VideoMetric.video_id == video.id)
            .filter(or_(VideoMetric.recorded_at <= now, VideoMetric.recorded_at.is_(None)))
            .order_by(VideoMetric.recorded_at.desc(), VideoMetric.id.desc())
            .first()
        )
        if metric is None:
            continue
        totals["views"] += int(_value(metric.views_count))
        totals["likes"] += int(_value(metric.likes_count))
        totals["comments"] += int(_value(metric.comments_count))
        score = calculate_video_metric_score(metric.views_count, metric.likes_count, metric.comments_count)
        if score > top_score:
            top_score = score
            top_video_id = video.youtube_video_id

    cache = (
        db.query(AnalyticsCache)
        .filter(AnalyticsCache.source_id == source.id, AnalyticsCache.date == date)
        .first()
    )
    if cache is None:
        cache = AnalyticsCache(source_id=source.id, date=date)
        db.add(cache)
    total_videos = len(videos)
    cache.total_videos = total_videos
    cache.total_views = totals["views"]
    cache.total_likes = totals["likes"]
    cache.total_comments = totals["comments"]
    cache.avg_views_per_video = totals["views"] / total_videos if total_videos else 0
    cache.avg_likes_per_video = totals["likes"] / total_videos if total_videos else 0
    cache.avg_comments_per_video = totals["comments"] / total_videos if total_videos else 0
    cache.top_video_id = top_video_id
    previous_cache = (
        db.query(AnalyticsCache)
        .filter(AnalyticsCache.source_id == source.id, AnalyticsCache.date < date)
        .order_by(AnalyticsCache.date.desc(), AnalyticsCache.id.desc())
        .first()
    )
    source_score = calculate_source_score(
        cache.avg_views_per_video,
        cache.avg_likes_per_video,
        cache.avg_comments_per_video,
    )
    previous_score = (
        calculate_source_score(
            previous_cache.avg_views_per_video,
            previous_cache.avg_likes_per_video,
            previous_cache.avg_comments_per_video,
        )
        if previous_cache is not None
        else 0
    )
    cache.growth_rate = round(((source_score - previous_score) / previous_score) * 100, 2) if previous_score else 0
    source.schedule_tier = calculate_source_schedule_tier(source_score, cache.growth_rate)
    cache.cached_at = now
    return cache
