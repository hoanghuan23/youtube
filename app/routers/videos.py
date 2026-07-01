from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Video, VideoMetric
from app.schemas.videos import VideoMetricRead, VideoRead


router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("", response_model=list[VideoRead])
def list_videos(
    source_id: int | None = Query(default=None),
    is_tracked: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Video]:
    query = db.query(Video)
    if source_id is not None:
        query = query.filter(Video.source_id == source_id)
    if is_tracked is not None:
        query = query.filter(Video.is_tracked.is_(is_tracked))
    return query.order_by(Video.published_at.desc(), Video.id.desc()).all()


@router.get("/{video_id}", response_model=VideoRead)
def get_video(video_id: int, db: Session = Depends(get_db)) -> Video:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/{video_id}/metrics", response_model=list[VideoMetricRead])
def get_video_metrics(video_id: int, db: Session = Depends(get_db)) -> list[VideoMetric]:
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return (
        db.query(VideoMetric)
        .filter(VideoMetric.video_id == video_id)
        .order_by(VideoMetric.recorded_at.desc(), VideoMetric.id.desc())
        .all()
    )
