from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship

from app.database import Base


class VideoMetric(Base):
    __tablename__ = "video_metrics"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    views_count = Column(Integer)
    likes_count = Column(Integer)
    comments_count = Column(Integer)
    recorded_at = Column(DateTime)
    job_id = Column(Integer, ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))

    video = relationship("Video", back_populates="metrics")
    job = relationship("PipelineJob", back_populates="metrics")
