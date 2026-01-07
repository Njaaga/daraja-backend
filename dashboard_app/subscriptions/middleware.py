# middleware/subscription.py

from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from tenants.middleware import get_current_tenant
from subscriptions.models import TenantSubscription
from dashboards.models import ApiDataSource, Dataset, Dashboard, Group
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
            request.subscription = (
                TenantSubscription.objects
                .filter(tenant=tenant, active=True)
                .order_by("-end_date")
                .first()
            )

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
        "/api/subscription/stripe-webhook/",
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
        path = request.path.rstrip("/")

        # Allow exempt paths
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix.rstrip("/")):
                return None

        tenant = get_current_tenant()
        if not tenant:
            return None  # No tenant, nothing to enforce

        # Get latest active subscription
        sub = (
            TenantSubscription.objects
            .filter(tenant=tenant, active=True)
            .order_by("-end_date")
            .first()
        )

        if not sub:
            return self._block(request, "NO_ACTIVE_SUBSCRIPTION")

        # Expiration check
        if sub.end_date and sub.end_date < timezone.now().date():
            return self._block(request, "SUBSCRIPTION_EXPIRED")

        # Get plan limits directly from DB
        plan = sub.plan
        limits = {
            "api_sources": plan.max_api_rows if plan else 0,
            "datasets": plan.max_datasets if plan else 0,
            "dashboards": plan.max_dashboards if plan else 0,
            "groups": plan.max_groups if plan else 0,
            "users": plan.max_users if plan else 0,
        }

        # Enforce plan quotas (POST only)
        if request.method == "POST":
            if path.startswith("/api/api-sources"):
                if ApiDataSource.objects.filter(tenant=tenant).count() >= limits["api_sources"]:
                    return self._block(request, "API_SOURCES_LIMIT_REACHED")

            if path.startswith("/api/datasets"):
                if Dataset.objects.filter(tenant=tenant).count() >= limits["datasets"]:
                    return self._block(request, "DATASETS_LIMIT_REACHED")

            if path.startswith("/api/dashboards"):
                if Dashboard.objects.filter(tenant=tenant).count() >= limits["dashboards"]:
                    return self._block(request, "DASHBOARDS_LIMIT_REACHED")

            if path.startswith("/api/groups"):
                if Group.objects.filter(tenant=tenant).count() >= limits["groups"]:
                    return self._block(request, "GROUPS_LIMIT_REACHED")

            if path.startswith("/api/users/invite"):
                if TenantUser.objects.filter(tenant=tenant).count() >= limits["users"]:
                    return self._block(request, "USERS_LIMIT_REACHED")

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
