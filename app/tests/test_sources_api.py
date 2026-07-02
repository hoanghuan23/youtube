import pytest

from app.models import Video, VideoMetric
from app.routers import sources as sources_router
from app.services.scraper_service import crawl_source_with_videos
from app.services.youtube_client import YouTubeVideoItem


@pytest.fixture(autouse=True)
def mock_channel_info(monkeypatch):
    monkeypatch.setattr(sources_router.youtube_channel_about, "extract_channel_info", lambda _url: None)

    async def fake_crawl_source(_db, _source, max_count=30):
        return None

    monkeypatch.setattr(sources_router, "crawl_source", fake_crawl_source)


def test_health_and_source_crud(client):
    assert client.get("/health").json() == {"status": "ok"}

    payload = {"source_type": "channel", "identifier": "@demo", "display_name": "Demo"}
    created = client.post("/sources", json=payload)
    assert created.status_code == 201
    source_id = created.json()["id"]
    assert created.json()["identifier"] == "demo"
    assert created.json()["subscriber_count"] is None
    assert created.json()["view_count"] is None

    duplicate = client.post("/sources", json=payload)
    assert duplicate.status_code == 400

    listed = client.get("/sources")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = client.patch(f"/sources/{source_id}", json={"display_name": "Updated"})
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Updated"

    deleted = client.delete(f"/sources/{source_id}")
    assert deleted.status_code == 204


def test_invalid_source_type_rejected(client):
    response = client.post("/sources", json={"source_type": "user", "identifier": "demo"})
    assert response.status_code == 422


def test_schedule_override_only_updates_via_patch(client):
    created = client.post(
        "/sources",
        json={
            "source_type": "channel",
            "identifier": "@demo",
            "schedule_override_minutes": 1,
        },
    )
    assert created.status_code == 201
    assert created.json()["schedule_override_minutes"] is None

    source_id = created.json()["id"]
    patched = client.patch(f"/sources/{source_id}", json={"schedule_override_minutes": 1})
    assert patched.status_code == 200
    assert patched.json()["schedule_override_minutes"] == 1


def test_create_channel_source_updates_source_metrics(client, monkeypatch):
    def fake_extract_channel_info(url):
        assert url == "https://www.youtube.com/@demo"
        return {
            "channel_title": "Demo Channel",
            "subscriber_count": 123_000,
            "view_count": 4_560_000,
        }

    monkeypatch.setattr(sources_router.youtube_channel_about, "extract_channel_info", fake_extract_channel_info)

    created = client.post("/sources", json={"source_type": "channel", "identifier": "@demo"})

    assert created.status_code == 201
    assert created.json()["display_name"] == "Demo Channel"
    assert created.json()["subscriber_count"] == 123_000
    assert created.json()["view_count"] == 4_560_000

    listed = client.get("/sources")
    assert listed.status_code == 200
    assert listed.json()[0]["subscriber_count"] == 123_000
    assert listed.json()[0]["view_count"] == 4_560_000


def test_create_channel_source_keeps_null_metrics_when_fetch_fails(client, monkeypatch):
    def raise_extract_channel_info(_url):
        raise RuntimeError("youtube unavailable")

    monkeypatch.setattr(sources_router.youtube_channel_about, "extract_channel_info", raise_extract_channel_info)

    created = client.post("/sources", json={"source_type": "channel", "identifier": "@demo"})

    assert created.status_code == 201
    assert created.json()["subscriber_count"] is None
    assert created.json()["view_count"] is None


def test_create_non_channel_source_does_not_fetch_channel_info(client, monkeypatch):
    def raise_extract_channel_info(_url):
        raise AssertionError("channel info should not be fetched")

    monkeypatch.setattr(sources_router.youtube_channel_about, "extract_channel_info", raise_extract_channel_info)

    keyword = client.post("/sources", json={"source_type": "keyword", "identifier": "python"})
    playlist = client.post("/sources", json={"source_type": "playlist", "identifier": "PL123"})

    assert keyword.status_code == 201
    assert keyword.json()["subscriber_count"] is None
    assert keyword.json()["view_count"] is None
    assert playlist.status_code == 201
    assert playlist.json()["subscriber_count"] is None
    assert playlist.json()["view_count"] is None


def test_create_source_bootstrap_crawls_videos(client, db_session, monkeypatch):
    async def fake_crawl_source(db, source, max_count=30):
        return crawl_source_with_videos(
            db,
            source,
            [
                YouTubeVideoItem(
                    youtube_video_id="abc123",
                    youtube_url="https://www.youtube.com/watch?v=abc123",
                    title="Demo",
                    metrics={"views_count": 100, "likes_count": 10, "comments_count": 2},
                )
            ],
        )

    monkeypatch.setattr(sources_router, "crawl_source", fake_crawl_source)

    created = client.post("/sources", json={"source_type": "channel", "identifier": "@demo"})

    assert created.status_code == 201
    assert db_session.query(Video).count() == 1
    assert db_session.query(VideoMetric).count() == 1


def test_create_channel_source_from_videos_url_preserves_channel_and_url(client):
    created = client.post("/sources", json={"source_type": "channel", "identifier": "https://www.youtube.com/@vtv24/videos"})

    assert created.status_code == 201
    assert created.json()["identifier"] == "vtv24"
    assert created.json()["youtube_url"] == "https://www.youtube.com/@vtv24/videos"
