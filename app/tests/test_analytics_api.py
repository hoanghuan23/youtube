from datetime import datetime

from app.models import AnalyticsCache, Source


def test_analytics_endpoint_returns_cached_rows(client, db_session):
    source = Source(source_type="keyword", identifier="python", is_active=True, is_accessible=True, created_at=datetime.utcnow())
    db_session.add(source)
    db_session.flush()
    db_session.add(
        AnalyticsCache(
            source_id=source.id,
            date=datetime(2026, 1, 1),
            total_videos=1,
            total_views=100,
            total_likes=10,
            total_comments=1,
            cached_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    response = client.get(f"/analytics/sources/{source.id}")

    assert response.status_code == 200
    assert response.json()[0]["total_videos"] == 1
