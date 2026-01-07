# middleware/subscription.py

from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from tenants.middleware import get_current_tenant
from subscriptions.models import TenantSubscription
from .utils.subscription_limits import RESOURCE_MAP

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

    # Paths that MUST NEVER be blocked (Stripe, auth, public)
    EXEMPT_PREFIXES = [
        "/admin",
        "/static",
        "/media",

        "/api/tenants/login",
        "/api/tenants/signup",
        "/api/tenants/verify-email",
        "/api/logout",

        # Stripe (CRITICAL)
        "/api/subscription/stripe-webhook",

        # Subscription setup / billing
        "/api/subscription/plans",
        "/api/subscription/status",
        "/api/subscription/activate",
        "/api/subscription/select-plan",
        "/api/subscription/create-setup-intent",
        "/api/subscription/create-checkout-session",
        "/api/subscription/list-payment-methods",
        "/api/subscription/list-invoices",
    ]

    def process_request(self, request):
        # --------------------------------------------------
        # Normalize path ONCE
        # --------------------------------------------------
        path = request.path.rstrip("/")

        # --------------------------------------------------
        # Always allow exempt paths
        # --------------------------------------------------
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix.rstrip("/")):
                return None

        tenant = get_current_tenant()
        if not tenant:
            return None  # no tenant, nothing to enforce

        # --------------------------------------------------
        # Get latest active subscription
        # --------------------------------------------------
        sub = (
            TenantSubscription.objects
            .filter(tenant=tenant, active=True)
            .order_by("-end_date")
            .first()
        )

        if not sub:
            return self._block(request, "NO_ACTIVE_SUBSCRIPTION")

        # --------------------------------------------------
        # Expiration check
        # --------------------------------------------------
        if sub.end_date and sub.end_date < timezone.now().date():
            return self._block(request, "SUBSCRIPTION_EXPIRED")

        # --------------------------------------------------
        # Enforce plan quotas (POST only)
        # --------------------------------------------------
        plan_name = sub.plan.name if sub.plan else None
        limits = RESOURCE_MAP.get(plan_name, {})

        if request.method == "POST":

            if path.startswith("/api/api-sources"):
                if ApiDataSource.objects.filter(tenant=tenant).count() >= limits.get("api_sources", 0):
                    return self._block(request, "API_SOURCES_LIMIT_REACHED")

            if path.startswith("/api/datasets"):
                if Dataset.objects.filter(tenant=tenant).count() >= limits.get("datasets", 0):
                    return self._block(request, "DATASETS_LIMIT_REACHED")

            if path.startswith("/api/dashboards"):
                if Dashboard.objects.filter(tenant=tenant).count() >= limits.get("dashboards", 0):
                    return self._block(request, "DASHBOARDS_LIMIT_REACHED")

            if path.startswith("/api/groups"):
                if Group.objects.filter(tenant=tenant).count() >= limits.get("groups", 0):
                    return self._block(request, "GROUPS_LIMIT_REACHED")

            if path.startswith("/api/users/invite"):
                if TenantUser.objects.filter(tenant=tenant).count() >= limits.get("users", 0):
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
