from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import KPI
from .serializers import KPISerializer

from tenants.middleware import get_current_tenant

from metrics.engine.metric_engine import MetricEngine


class KPIViewSet(ModelViewSet):
    serializer_class = KPISerializer

    def get_queryset(self):
        tenant = get_current_tenant()

        if not tenant:
            return KPI.objects.none()

        return KPI.objects.filter(
            tenant_id=tenant.id
        )

    @action(detail=False, methods=["get"])
    def executive(self, request):

        tenant = get_current_tenant()

        if not tenant:
            return Response([])

        kpis = KPI.objects.filter(
            tenant_id=tenant.id,
            active=True
        )

        dashboard = []

        for kpi in kpis:

            metric = kpi.metric

            current_value = MetricEngine.calculate(metric, request)

            if current_value >= float(kpi.warning_threshold):
                status = "healthy"
            elif current_value >= float(kpi.critical_threshold):
                status = "warning"
            else:
                status = "critical"

            dashboard.append({
                "id": kpi.id,
                "name": kpi.name,
                "current": current_value,
                "target": float(kpi.target_value),
                "warning": float(kpi.warning_threshold),
                "critical": float(kpi.critical_threshold),
                "status": status,
            })

        return Response(dashboard)


