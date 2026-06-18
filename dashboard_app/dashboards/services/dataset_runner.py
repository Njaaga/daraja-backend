# dashboards/services/dataset_runner.py

if request is None:
    print(
        "[DATASET RUNNER] "
        "Running without request context"
    )
def run_dataset(dataset, request):
    """
    Must reuse existing dataset execution logic.
    DO NOT invent new logic here.
    """
    from dashboards.views import DatasetViewSet

    view = DatasetViewSet()
    view.request = request

    return view._run_dataset(dataset)
