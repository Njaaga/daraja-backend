from rest_framework.routers import DefaultRouter
from .views import KPIViewSet

router = DefaultRouter()
router.register(r"", KPIViewSet, basename="kpi")

urlpatterns = router.urls
