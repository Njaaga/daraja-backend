from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.views.decorators.csrf import csrf_exempt

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

from .oauth.quickbooks import quickbooks_connect, quickbooks_callback

# DRF router for protected endpoints
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'dashboards', DashboardViewSet, basename="dashboard")
router.register(r'groups', GroupViewSet, basename="group")
router.register(r'api-sources', ApiDataSourceViewSet, basename="api-source")
router.register(r'datasets', DatasetViewSet, basename="dataset")
router.register(r'charts', ChartViewSet, basename="chart")

urlpatterns = [
    # -----------------------------
    # Public QuickBooks OAuth endpoints
    # -----------------------------
    path("qb/oauth/connect/", csrf_exempt(quickbooks_connect)),
    path("qb/oauth/callback/", csrf_exempt(quickbooks_callback)),


    # -----------------------------
    # Current user info
    # -----------------------------
    path('users/me/', CurrentUserView.as_view(), name='current-user'),

    # -----------------------------
    # Password / auth management
    # -----------------------------
    path("set-password/", SetPasswordView.as_view(), name="set-password"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),

    # -----------------------------
    # Support
    # -----------------------------
    path("support/", support_request),
    path("support-guest/", support_guest),

    # -----------------------------
    # Ad-hoc dataset execution
    # -----------------------------
    path("datasets/run/", DatasetRunAdhocView.as_view(), name="datasets-adhoc-run"),

    # -----------------------------
    # Protected DRF router endpoints
    # -----------------------------
    path("", include(router.urls)),
]
