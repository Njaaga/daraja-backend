from metrics.models import Metric
from metrics.models import MetricSnapshot

from metrics.engine.metric_engine import MetricEngine


class SnapshotService:

    @staticmethod
    def capture_metric(metric):

        try:

            value = MetricEngine.calculate(
                metric,
                request=None
            )

            MetricSnapshot.objects.create(
                tenant=metric.tenant,
                metric=metric,
                value=value
            )

            print(
                f"[SNAPSHOT] "
                f"{metric.name} = {value}"
            )

            return value

        except Exception as e:

            print(
                f"[SNAPSHOT ERROR] "
                f"{metric.name}: {e}"
            )

            return None

    @staticmethod
    def capture_all():

        metrics = Metric.objects.all()

        count = 0

        for metric in metrics:

            SnapshotService.capture_metric(
                metric
            )

            count += 1

        print(
            f"[SNAPSHOT COMPLETE] "
            f"{count} metrics captured"
        )

        return count
