from tenants.middleware import get_current_tenant
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
    
        tenant = get_current_tenant()
    
        return Response({
            "tenant_id": tenant.id if tenant else None,
            "tenant_name": str(tenant) if tenant else None,
            "total_kpis": KPI.objects.count(),
            "tenant_kpis": KPI.objects.filter(
                tenant_id=tenant.id if tenant else None
            ).count(),
        })

        data = []

        for kpi in kpis:
            data.append({
                "id": kpi.id,
                "name": kpi.name,
                "current": 0,
                "target": float(kpi.target_value),
                "warning": float(kpi.warning_threshold),
                "critical": float(kpi.critical_threshold),
                "status": "healthy",
            })

        return Response(data)
