import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Source
from app.schemas.sources import SourceCreate, SourceRead, SourceUpdate
from app.services import youtube_channel_about
from app.services.scraper_service import crawl_source


router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger("youtube_api.sources")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_identifier(source_type: str, identifier: str) -> str:
    value = identifier.strip()
    if source_type == "channel":
        if "youtube.com" in value:
            parts = [part for part in urlparse(value).path.split("/") if part]
            for part in parts:
                if part.startswith("@"):
                    return part.lstrip("@")
            if len(parts) > 1 and parts[0] in {"channel", "c", "user"}:
                return parts[1]
            if parts:
                return parts[0]
        return value.lstrip("@")
    if source_type == "keyword":
        return value
    return value


def _source_url(source_type: str, identifier: str, explicit_url: str | None = None) -> str | None:
    if explicit_url:
        return explicit_url.strip().rstrip("/")
    if source_type == "channel":
        return f"https://www.youtube.com/@{identifier}"
    if source_type == "playlist":
        return f"https://www.youtube.com/playlist?list={identifier}"
    return None


def _fetch_channel_info(youtube_url: str | None) -> dict | None:
    if not youtube_url:
        return None
    try:
        return youtube_channel_about.extract_channel_info(youtube_url)
    except Exception as exc:
        logger.warning("Unable to fetch YouTube channel info for %s: %s", youtube_url, exc)
        return None


def _channel_identifier_from_info(channel_info: dict | None) -> str | None:
    if not channel_info:
        return None
    identifier = channel_info.get("identifier")
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip().lstrip("@")
    channel_handle = channel_info.get("channel_handle")
    if isinstance(channel_handle, str) and channel_handle.strip():
        return channel_handle.strip().lstrip("@")
    youtube_channel_id = channel_info.get("youtube_channel_id")
    if isinstance(youtube_channel_id, str) and youtube_channel_id.strip():
        return youtube_channel_id.strip()
    return None


def _channel_display_name_from_info(channel_info: dict | None) -> str | None:
    if not channel_info:
        return None
    for key in ("display_name", "channel_title"):
        value = channel_info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> Source:
    raw_identifier = payload.identifier or payload.youtube_url
    if raw_identifier is None:
        raise HTTPException(status_code=422, detail="identifier or youtube_url is required")

    identifier = _normalize_identifier(payload.source_type, raw_identifier)
    explicit_url = payload.youtube_url
    if payload.source_type == "channel" and not explicit_url and raw_identifier.strip().startswith(("http://", "https://")):
        explicit_url = raw_identifier
    youtube_url = _source_url(payload.source_type, identifier, explicit_url)
    existing = (
        db.query(Source)
        .filter(Source.youtube_url == youtube_url)
        .first()
        if youtube_url
        else None
    )
    if existing:
        raise HTTPException(status_code=400, detail="Source already exists")

    channel_info = _fetch_channel_info(youtube_url) if payload.source_type == "channel" else None
    if payload.source_type == "channel":
        identifier = _channel_identifier_from_info(channel_info) or identifier
        if not identifier:
            raise HTTPException(status_code=400, detail="Unable to extract YouTube channel identifier")
    source = Source(
        source_type=payload.source_type,
        identifier=identifier,
        display_name=payload.display_name or _channel_display_name_from_info(channel_info),
        youtube_url=youtube_url,
        subscriber_count=(channel_info or {}).get("subscriber_count"),
        view_count=(channel_info or {}).get("view_count"),
        is_active=True,
        is_accessible=True,
        max_days_old=payload.max_days_old,
        created_at=_now(),
    )
    db.add(source)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Source already exists") from exc
    db.refresh(source)
    await crawl_source(db, source)
    db.refresh(source)
    return source


@router.get("", response_model=list[SourceRead])
def list_sources(
    is_active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Source]:
    query = db.query(Source)
    if is_active is not None:
        query = query.filter(Source.is_active.is_(is_active))
    return query.order_by(Source.id.desc()).all()


@router.get("/{source_id}", response_model=SourceRead)
def get_source(source_id: int, db: Session = Depends(get_db)) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.patch("/{source_id}", response_model=SourceRead)
def update_source(source_id: int, payload: SourceUpdate, db: Session = Depends(get_db)) -> Source:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid source update") from exc
    db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)) -> None:
    source = db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot delete source with related data") from exc
