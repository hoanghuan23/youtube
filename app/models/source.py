from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("source_type", "identifier", name="uq_youtube_source"),)

    id = Column(Integer, primary_key=True)
    source_type = Column(String(20), nullable=False)
    identifier = Column(String(255), nullable=False)
    display_name = Column(String(255))
    youtube_url = Column(String(500))
    subscriber_count = Column(Integer)
    view_count = Column(Integer)
    is_active = Column(Boolean, default=True)
    is_accessible = Column(Boolean)
    max_days_old = Column(Integer)
    created_at = Column(DateTime)
    last_scraped = Column(DateTime)
    next_scrape = Column(DateTime)
    schedule_tier = Column(Integer)
    schedule_override_minutes = Column(Integer)

    videos = relationship("Video", back_populates="source")
    analytics = relationship("AnalyticsCache", back_populates="source")
    jobs = relationship("PipelineJob", back_populates="source")
    logs = relationship("PipelineLog", back_populates="source")
