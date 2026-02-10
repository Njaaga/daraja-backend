from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from subscriptions import views as sub_views
from dashboards.oauth.quickbooks import quickbooks_connect, quickbooks_callback

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/oauth/quickbooks/connect/', csrf_exempt(quickbooks_connect)),
    path('api/oauth/quickbooks/callback/', csrf_exempt(quickbooks_callback)),
    path('api/tenants/', include('tenants.urls')),
    path('api/', include('dashboards.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("api/subscription/", include("subscriptions.urls")),
]

