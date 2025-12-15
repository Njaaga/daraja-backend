from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet,
    DashboardViewSet,
    GroupViewSet,
    PasswordSetupView,
    ApiDataSourceViewSet,
    DatasetViewSet,
    DatasetRunAdhocView,
    ChartViewSet,
    CurrentUserView,
)

# =========================================================
# PROTECTED ROUTES (REQUIRE AUTH via DRF)
# =========================================================
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'dashboards', DashboardViewSet, basename="dashboard")
router.register(r'groups', GroupViewSet, basename="group")
router.register(r'api-sources', ApiDataSourceViewSet, basename="api-source")
router.register(r'datasets', DatasetViewSet, basename="dataset")
router.register(r'charts', ChartViewSet, basename="chart")

urlpatterns = [

    # all secured authenticated API endpoints
    path("", include(router.urls)),


    # =========================================================
    # PUBLIC ENDPOINT (NO AUTH REQUIRED)
    # standalone view -> does NOT inherit router permissions
    # =========================================================
    path("set-password/", PasswordSetupView.as_view(), name="set-password"),

    # dataset adhoc execution endpoint
    path("datasets/run/", DatasetRunAdhocView.as_view(), name="datasets-adhoc-run"),

    path('users/me/', CurrentUserView.as_view(), name='current-user'),
]
