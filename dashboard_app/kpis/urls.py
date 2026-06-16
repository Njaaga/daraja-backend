from rest_framework.routers import DefaultRouter
from .views import KPIViewSet

router = DefaultRouter()
router.register("", KPIViewSet)

urlpatterns = router.urls
