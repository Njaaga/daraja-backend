from dashboards.models import Dataset
from dashboards.services.dataset_runner import run_dataset


class MetricEngine:

    @staticmethod
    def calculate(metric, request):

        try:
            dataset = Dataset.objects.get(
                name=metric.dataset
            )

        except Dataset.DoesNotExist:
            return 0

        rows = run_dataset(dataset, request)

        if not rows:
            return 0

        field = metric.field_name

        values = []

        for row in rows:

            value = row.get(field)

            if value is None:
                continue

            try:
                values.append(float(value))
            except Exception:
                pass

        if metric.aggregation == "sum":
            return sum(values)

        if metric.aggregation == "avg":
            return (
                sum(values) / len(values)
                if values
                else 0
            )

        if metric.aggregation == "count":
            return len(values)

        if metric.aggregation == "max":
            return max(values) if values else 0

        if metric.aggregation == "min":
            return min(values) if values else 0

        return 0
