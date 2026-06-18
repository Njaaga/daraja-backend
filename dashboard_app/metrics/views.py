from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Metric
from .services.trend_service import TrendService


class MetricViewSet(viewsets.ReadOnlyModelViewSet):

    queryset = Metric.objects.all()

    @action(
        detail=True,
        methods=["get"]
    )
    def trend(self, request, pk=None):

        metric = self.get_object()

        trend = TrendService.get_trend(
            metric=metric,
            days=30
        )

        return Response(trend)
