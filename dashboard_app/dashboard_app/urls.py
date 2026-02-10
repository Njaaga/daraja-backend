# dashboard_app/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from dashboards.oauth.quickbooks import (
    quickbooks_connect,
    quickbooks_callback,
)

urlpatterns = [
    # --------------------
    # Admin
    # --------------------
    path("admin/", admin.site.urls),

    # --------------------
    # QuickBooks OAuth (PUBLIC)
    # --------------------
    path(
        "api/oauth/quickbooks/connect/",
        csrf_exempt(quickbooks_connect),
        name="quickbooks-connect",
    ),
    path(
        "api/oauth/quickbooks/callback/",
        csrf_exempt(quickbooks_callback),
        name="quickbooks-callback",
    ),

    # --------------------
    # Auth / tenants
    # --------------------
    path("api/tenants/", include("tenants.urls")),

    # --------------------
    # Dashboards app
    # --------------------
    path("api/", include("dashboards.urls")),

    # --------------------
    # JWT
    # --------------------
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),

    # --------------------
    # Subscriptions
    # --------------------
    path("api/subscription/", include("subscriptions.urls")),
]
