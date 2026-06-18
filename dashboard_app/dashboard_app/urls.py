from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from subscriptions import views as sub_views
from django.views.decorators.csrf import csrf_exempt

from dashboards.oauth.quickbooks import (
    quickbooks_connect,
    quickbooks_callback,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    path(
        "api/oauth/quickbooks/connect/",
        csrf_exempt(quickbooks_connect),
        name="quickbooks-connect"
    ),
    path(
        "api/oauth/quickbooks/callback/",
        csrf_exempt(quickbooks_callback),
        name="quickbooks-callback"
    ),
    
    path('api/', include('dashboards.urls')),
    path('api/tenants/', include('tenants.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("api/subscription/", include("subscriptions.urls")),
    path("api/kpis/", include("kpis.urls")),
    path("api/metrics/", include("metrics.urls")),
]

