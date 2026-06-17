from dashboards.models import Dataset
from dashboards.services.dataset_runner import run_dataset


class MetricEngine:

    @staticmethod
    def calculate(metric, request):

        print("\n" + "=" * 60)
        print(f"CALCULATING METRIC: {metric.name}")
        print(f"Dataset: {metric.dataset}")
        print(f"Field: {metric.field_name}")
        print(f"Aggregation: {metric.aggregation}")
        print("=" * 60)

        try:
            dataset = Dataset.objects.get(
                name=metric.dataset
            )

            print(
                f"Dataset Found -> ID={dataset.id} "
                f"Name={dataset.name}"
            )

        except Dataset.DoesNotExist:

            print(
                f"ERROR: Dataset '{metric.dataset}' not found"
            )

            return 0

        try:

            rows = run_dataset(
                dataset,
                request
            )

            print(
                f"Dataset returned {len(rows) if rows else 0} rows"
            )

        except Exception as e:

            print(
                f"ERROR running dataset: {str(e)}"
            )

            return 0

        if not rows:

            print(
                f"No rows returned for metric '{metric.name}'"
            )

            return 0

        field = metric.field_name

        values = []

        for idx, row in enumerate(rows):

            if idx < 3:
                print(f"Sample Row {idx + 1}: {row}")

            value = row.get(field)

            if value is None:
                continue

            try:
                values.append(float(value))
            except Exception:
                print(
                    f"Skipping non-numeric value: {value}"
                )

        print(
            f"Numeric values found: {len(values)}"
        )

        if values:
            print(
                f"Sample values: {values[:5]}"
            )

        result = 0

        if metric.aggregation == "sum":

            result = sum(values)

        elif metric.aggregation == "avg":

            result = (
                sum(values) / len(values)
                if values
                else 0
            )

        elif metric.aggregation == "count":

            result = len(values)

        elif metric.aggregation == "max":

            result = max(values) if values else 0

        elif metric.aggregation == "min":

            result = min(values) if values else 0

        print(
            f"FINAL RESULT ({metric.aggregation}) = {result}"
        )

        print("=" * 60 + "\n")

        return result
