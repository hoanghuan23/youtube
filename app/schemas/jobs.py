from datetime import datetime

from app.schemas.base import ORMBaseModel


class PipelineLogRead(ORMBaseModel):
    id: int
    job_id: int | None = None
    source_id: int | None = None
    log_level: str
    message: str
    error_type: str | None = None
    error_details: str | None = None
    created_at: datetime | None = None


class PipelineJobRead(ORMBaseModel):
    id: int
    job_type: str
    source_id: int | None = None
    status: str
    videos_found: int
    videos_new: int
    items_total: int
    items_updated: int
    items_failed: int
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PipelineJobDetail(PipelineJobRead):
    logs: list[PipelineLogRead] = []
