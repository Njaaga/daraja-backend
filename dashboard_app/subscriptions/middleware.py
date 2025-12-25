# middleware/subscription.py
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from tenants.middleware import get_current_tenant
from subscriptions.models import TenantSubscription
from .utils.subscription_limits import RESOURCE_MAP
from django.contrib.auth import get_user_model
User = get_user_model()
from dashboards.models import ApiDataSource, Dataset, Dashboard, Group  # example model to enforce quotas
from tenants.models import TenantUser

class TenantSubscriptionMiddleware:
    """
    After TenantMiddleware runs, attach request.subscription (or None)
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = get_current_tenant()
        request.subscription = None
        if tenant:
            request.subscription = TenantSubscription.objects.filter(
                tenant=tenant, active=True
            ).order_by('-end_date').first()
        return self.get_response(request)


class SubscriptionEnforcementMiddleware(MiddlewareMixin):
    """
    Enforces subscription rules for tenants, including active subscription,
    expiration, and plan-based quotas.
    """

    FREE_PATHS = [
        "/api/tenants/login/",
        "/api/tenants/verify-email/",
        "/api/logout/",
        "/admin/",
        "/api/subscription/plans/",
        "/api/subscription/status/",
        "/api/subscription/activate/",
        "/api/subscription/select-plan/",
        "/api/subscription/create-setup-intent/",
        "/api/subscription/stripe/create-checkout/",
        "/api/subscription/stripe/webhook/",
        "/api/subscription/stripe/confirm/",
        "/api/subscription/list-payment-methods/",
        "/api/subscription/list-invoices/",
        "/api/subscription/create-checkout-session/",
        "/api/api-sources/",
        "/api/datasets/",
        "/api/dashboards/",
        "/api/groups/",
        "/api/users/invite",
    ]

    def process_request(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return None  # no tenant, nothing to enforce

        # Allow free public paths
        for path in self.FREE_PATHS:
            if request.path.startswith(path):
                return None

        # Get latest active subscription
        sub = TenantSubscription.objects.filter(
            tenant=tenant, active=True
        ).order_by('-end_date').first()

        if not sub:
            return self._block(request, "NO_ACTIVE_SUBSCRIPTION")

        # Check expiration
        if sub.end_date and sub.end_date < timezone.now().date():
            return self._block(request, "SUBSCRIPTION_EXPIRED")

        # Optional: enforce quotas per plan
        plan_name = sub.plan.name if sub.plan else None
        if plan_name and plan_name in RESOURCE_MAP:
            limits = RESOURCE_MAP[plan_name]

            # Example: limit API sources
            if request.path.startswith("/api/api-sources") and request.method == "POST":
                current_count = ApiDataSource.objects.filter(tenant=tenant).count()
                if current_count >= limits.get("api_sources", 0):
                    return self._block(request, "API_SOURCES_LIMIT_REACHED")
                
            # Example: limit Datasets
            if request.path.startswith("/api/datasets") and request.method == "POST":
                current_count = Dataset.objects.filter(tenant=tenant).count()
                if current_count >= limits.get("datasets", 0):
                    return self._block(request, "DATASETS_LIMIT_REACHED")
                
            # Example: limit Groups
            if request.path.startswith("/api/dashboards") and request.method == "POST":
                current_count = Dashboard.objects.filter(tenant=tenant).count()
                if current_count >= limits.get("dashboards", 0):
                    return self._block(request, "DASHBOARDS_LIMIT_REACHED")
                
            if request.path.startswith("/api/groups") and request.method == "POST":
                current_count = Group.objects.filter(tenant=tenant).count()
                if current_count >= limits.get("groups", 0):
                    return self._block(request, "GROUPS_LIMIT_REACHED")
                
            if request.path.startswith("/api/users/invite") and request.method == "POST":
                current_count = TenantUser.objects.filter(tenant=tenant).count()
                if current_count >= limits.get("users", 0):
                    return self._block(request, "USERS_LIMIT_REACHED")

            # You can add other limits here: users, dashboards, datasets, etc.

        # Attach subscription to request for easy access in views
        request.subscription = sub
        return None

    def _block(self, request, reason):
        if request.path.startswith("/api/"):
            return JsonResponse(
                {"status": "subscription_blocked", "reason": reason},
                status=402,
            )
        return redirect("/subscription/select-plan/")
