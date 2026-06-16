from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import KPI
from .serializers import KPISerializer


class KPIViewSet(ModelViewSet):
    queryset = KPI.objects.all()
    serializer_class = KPISerializer

    @action(detail=False, methods=["get"])
    def executive(self, request):

        tenant_id = request.user.tenant_id

        kpis = KPI.objects.filter(
            tenant_id=tenant_id,
            active=True
        )

        data = []

        for kpi in kpis:
            data.append({
                "id": kpi.id,
                "name": kpi.name,
                "current": 0,  # temporary
                "target": float(kpi.target_value),
                "warning": float(kpi.warning_threshold),
                "critical": float(kpi.critical_threshold),
                "status": "healthy"
            })

        return Response(data)
