from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    youtube_channel_id = Column(String(100), nullable=False, unique=True)
    channel_handle = Column(String(255))
    channel_title = Column(String(255))
    channel_url = Column(String(500))
    thumbnail_url = Column(String(500))
    subscriber_count = Column(Integer)
    video_count = Column(Integer)
    view_count = Column(Integer)
    is_verified = Column(Boolean)
    description = Column(Text)
    created_at = Column(DateTime)
    last_updated = Column(DateTime)

    videos = relationship("Video", back_populates="channel")
