from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet,
    DashboardViewSet,
    GroupViewSet,
    SetPasswordView,
    ApiDataSourceViewSet,
    DatasetViewSet,
    DatasetRunAdhocView,
    ChartViewSet,
    CurrentUserView,
    ForgotPasswordView,
    ResetPasswordView,
    support_request,
    support_guest,
)


from django.contrib.auth import views as auth_views

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

    path('users/me/', CurrentUserView.as_view(), name='current-user'),
    
    # all secured authenticated API endpoints
    path("", include(router.urls)),

    path("set-password/", SetPasswordView.as_view(), name="set-password"),

    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),

    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),

    path("support/", support_request),

    path("support-guest/", support_guest),

    # =========================================================
    # PUBLIC ENDPOINT (NO AUTH REQUIRED)
    # standalone view -> does NOT inherit router permissions
    # =========================================================

    # dataset adhoc execution endpoint
    path("datasets/run/", DatasetRunAdhocView.as_view(), name="datasets-adhoc-run"),

]
