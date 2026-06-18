from rest_framework.routers import DefaultRouter

from .views import MetricViewSet

router = DefaultRouter()

router.register(
    r"",
    MetricViewSet,
    basename="metric"
)

urlpatterns = router.urls
