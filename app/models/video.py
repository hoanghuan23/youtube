from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"))
    youtube_video_id = Column(String(100), nullable=False, unique=True)
    youtube_url = Column(String(500), nullable=False)
    title = Column(String(500))
    description = Column(Text)
    published_at = Column(DateTime, nullable=False)
    duration_seconds = Column(Integer)
    video_type = Column(String(20), default="long")
    thumbnail_url = Column(String(500))
    created_at = Column(DateTime)
    is_tracked = Column(Boolean, default=True)
    tracking_until = Column(DateTime)
    is_deleted = Column(Boolean, default=False)
    last_metric_update = Column(DateTime)
    next_metric_update = Column(DateTime)
    metric_tier = Column(String(20), nullable=False, default="bootstrap")
    last_engagement_velocity = Column(Float)
    cold_check_count = Column(Integer, nullable=False, default=0)
    metric_scan_miss_count = Column(Integer, nullable=False, default=0)

    source = relationship("Source", back_populates="videos")
    channel = relationship("Channel", back_populates="videos")
    metrics = relationship("VideoMetric", back_populates="video", order_by="VideoMetric.recorded_at")
    comments = relationship("Comment", back_populates="video")
