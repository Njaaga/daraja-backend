# dashboards/services/dataset_runner.py

def run_dataset(dataset, request):
    """
    Must reuse existing dataset execution logic.
    DO NOT invent new logic here.
    """
    from dashboards.views import DatasetViewSet

    view = DatasetViewSet()
    view.request = request

    return view._run_dataset(dataset)
