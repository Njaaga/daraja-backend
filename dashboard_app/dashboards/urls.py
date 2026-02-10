# dashboards/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    UserViewSet,
    DashboardViewSet,
    GroupViewSet,
    ApiDataSourceViewSet,
    DatasetViewSet,
    DatasetRunAdhocView,
    ChartViewSet,
    CurrentUserView,
    SetPasswordView,
    ForgotPasswordView,
    ResetPasswordView,
    support_request,
    support_guest,
)

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("dashboards", DashboardViewSet)
router.register("groups", GroupViewSet)
router.register("api-sources", ApiDataSourceViewSet)
router.register("datasets", DatasetViewSet)
router.register("charts", ChartViewSet)

urlpatterns = [
    path("users/me/", CurrentUserView.as_view()),

    path("set-password/", SetPasswordView.as_view()),
    path("forgot-password/", ForgotPasswordView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),

    path("support/", support_request),
    path("support-guest/", support_guest),

    path("datasets/run/", DatasetRunAdhocView.as_view()),

    path("", include(router.urls)),
]
