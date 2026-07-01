from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    youtube_comment_id = Column(String(100), nullable=False, unique=True)
    commenter_id = Column(String(100))
    commenter_name = Column(String(255))
    commenter_channel_url = Column(String(500))
    comment_text = Column(Text)
    likes_count = Column(Integer)
    published_at = Column(DateTime)
    updated_at = Column(DateTime)
    last_updated = Column(DateTime)

    video = relationship("Video", back_populates="comments")
