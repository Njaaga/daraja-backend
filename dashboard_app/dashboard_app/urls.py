# project/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# Import QuickBooks endpoints
from dashboards.oauth.quickbooks import quickbooks_connect, quickbooks_callback

urlpatterns = [
    # ---------- Admin ----------
    path('admin/', admin.site.urls),

    # ---------- QuickBooks OAuth (public, CSRF exempt) ----------
    path('api/oauth/quickbooks/connect/', csrf_exempt(quickbooks_connect), name='quickbooks-connect'),
    path('api/oauth/quickbooks/callback/', csrf_exempt(quickbooks_callback), name='quickbooks-callback'),

    # ---------- Tenants (login, signup, etc.) ----------
    path('api/tenants/', include('tenants.urls')),

    # ---------- Dashboard & API endpoints ----------
    path('api/', include('dashboards.urls')),

    # ---------- JWT token endpoints ----------
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ---------- Subscriptions ----------
    path("api/subscription/", include("subscriptions.urls")),
]
