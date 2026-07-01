from datetime import datetime

from app.models import VideoMetric
from app.services.tier_service import metric_tier_from_metric, next_metric_update_at


def test_metric_tier_and_next_update():
    metric = VideoMetric(views_count=10_000, likes_count=2_000, comments_count=200)

    tier = metric_tier_from_metric(metric)
    next_update = next_metric_update_at(datetime(2026, 1, 1, 0, 0, 0), tier)

    assert tier == "medium"
    assert next_update == datetime(2026, 1, 1, 1, 0, 0)
