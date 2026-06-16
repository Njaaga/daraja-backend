from rest_framework.viewsets import ModelViewSet

from .models import KPI
from .serializers import KPISerializer


class KPIViewSet(ModelViewSet):
    queryset = KPI.objects.all()
    serializer_class = KPISerializer
