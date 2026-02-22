from rest_framework.response import Response


def run_dataset(dataset, request):
    """
    Executes a dataset and returns raw rows (list[dict])
    """

    source = dataset.source

    if source.provider != "quickbooks":
        return []

    if not source.bearer_token:
        return []

    # 🔴 IMPORTANT: this must be the SAME logic you had in DatasetViewSet._run_dataset
    rows = dataset.execute(
        request=request,
        filters=dataset.filters,
        joins=dataset.joins,
    )

    return rows if isinstance(rows, list) else []
