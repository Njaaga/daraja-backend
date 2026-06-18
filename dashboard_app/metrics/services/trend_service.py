from datetime import timedelta

from django.utils import timezone

from metrics.models import MetricSnapshot


class TrendService:

    @staticmethod
    def get_trend(metric, days=30):

        since = timezone.now() - timedelta(days=days)

        snapshots = (
            MetricSnapshot.objects
            .filter(
                metric=metric,
                recorded_at__gte=since
            )
            .order_by("recorded_at")
        )

        return [
            {
                "date": s.recorded_at.date(),
                "value": s.value
            }
            for s in snapshots
        ]
