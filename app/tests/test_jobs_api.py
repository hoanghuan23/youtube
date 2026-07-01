from datetime import datetime

from app.models import Source, Video


def test_jobs_api_crawl_and_get_job(client, monkeypatch):
    import app.services.scraper_service as scraper_service

    async def fake_channel_videos(self, identifier, max_count=30, since=None):
        return [
            {
                "video_id": "abc123",
                "url": "https://www.youtube.com/watch?v=abc123",
                "title": "Demo",
                "published_at": datetime.utcnow(),
                "metrics": {"views_count": 10, "likes_count": 1, "comments_count": 0},
            }
        ]

    monkeypatch.setattr(scraper_service.YouTubeClient, "get_channel_videos", fake_channel_videos)

    created = client.post("/sources", json={"source_type": "channel", "identifier": "demo"})
    source_id = created.json()["id"]
    job_response = client.post(f"/jobs/sources/{source_id}/crawl")

    assert job_response.status_code == 200
    assert job_response.json()["status"] == "done"
    assert job_response.json()["videos_new"] == 1

    detail = client.get(f"/jobs/{job_response.json()['id']}")
    assert detail.status_code == 200


def test_update_video_metric_job(client, db_session, monkeypatch):
    import app.services.metric_service as metric_service

    source = Source(source_type="channel", identifier="demo", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.flush()
    video = Video(
        source_id=source.id,
        youtube_video_id="abc123",
        youtube_url="https://www.youtube.com/watch?v=abc123",
        published_at=datetime.utcnow(),
        metric_tier="bootstrap",
    )
    db_session.add(video)
    db_session.commit()

    async def fake_fetch_metric(_video):
        return {"views_count": 20, "likes_count": 2, "comments_count": 1}

    monkeypatch.setattr(metric_service, "_fetch_metric", fake_fetch_metric)

    response = client.post(f"/jobs/videos/{video.id}/update-metric")
    assert response.status_code == 200
    assert response.json()["items_updated"] == 1
