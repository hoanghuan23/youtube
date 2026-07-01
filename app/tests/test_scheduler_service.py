from datetime import datetime

import pytest

from app.models import Source
from app.services import scheduler_service


@pytest.mark.asyncio
async def test_scheduler_picks_due_source(monkeypatch, db_session):
    source = Source(source_type="keyword", identifier="python", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.commit()

    async def fake_crawl_source(_db, _source, max_count=30):
        class Job:
            id = 99

        return Job()

    monkeypatch.setattr(scheduler_service, "crawl_source", fake_crawl_source)

    result = await scheduler_service.run_scheduler_cycle(db_session, now=datetime.utcnow(), source_limit=10, video_limit=10)

    assert result["sources_processed"] == 1
    assert result["source_job_ids"] == [99]
