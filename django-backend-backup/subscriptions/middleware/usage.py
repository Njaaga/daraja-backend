# subscriptions/middleware/usage.py
from django.utils.deprecation import MiddlewareMixin
from tenants.middleware import get_current_tenant
from dashboards.models import Dashboard  # adapt import paths
from tenants.models import TenantUser
from datasets.models import Dataset

class TenantUsageMiddleware(MiddlewareMixin):
    def process_request(self, request):
        tenant = get_current_tenant()
        request.tenant_usage = {}
        if not tenant:
            return None
        request.tenant_usage["dashboards_count"] = Dashboard.objects.filter(tenant=tenant).count()
        request.tenant_usage["users_count"] = TenantUser.objects.filter(tenant=tenant).count()
        request.tenant_usage["datasets_count"] = Dataset.objects.filter(tenant=tenant).count()
        # You can also store current api rows count if you persist that
        return None
