from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    __table_args__ = (UniqueConstraint("source_id", "date", name="uq_youtube_analytics_cache"),)

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)
    total_videos = Column(Integer)
    total_views = Column(Integer)
    total_likes = Column(Integer)
    total_comments = Column(Integer)
    avg_views_per_video = Column(Float)
    avg_likes_per_video = Column(Float)
    avg_comments_per_video = Column(Float)
    top_video_id = Column(String(100))
    growth_rate = Column(Float)
    cached_at = Column(DateTime)

    source = relationship("Source", back_populates="analytics")
