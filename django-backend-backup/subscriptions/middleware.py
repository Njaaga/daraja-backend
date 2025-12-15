# middleware/subscription.py
from .models import TenantSubscription
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from tenants.middleware import get_current_tenant
from .models import TenantSubscription

class TenantSubscriptionMiddleware:
    """
    After TenantMiddleware runs, this middleware attaches request.subscription (or None).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        request.subscription = None
        if tenant:
            try:
                request.subscription = TenantSubscription.objects.get(tenant=tenant)
            except TenantSubscription.DoesNotExist:
                request.subscription = None
        return self.get_response(request)



class SubscriptionEnforcementMiddleware(MiddlewareMixin):
    """
    Enforces subscription rules for tenants.
    """

    FREE_PATHS = [
        "/api/login/",
        "/api/logout/",
        "/admin/",
        "/api/subscription/plans/",
        "/api/subscription/status/",
        "/api/subscription/activate/",
        "/api/subscription/select-plan/",
        "/api/subscription/create-setup-intent/",  # ✅ REQUIRED
        "/api/subscription/stripe/create-checkout/",
        "/api/subscription/stripe/webhook/",
        "/api/subscription/stripe/confirm/",
        "/api/subscription/list-payment-methods/",
        "/api/subscription/list-invoices/",
        "/api/subscription/create-checkout-session/",
    ]



    def process_request(self, request):
        tenant = get_current_tenant()

        # No tenant found → do nothing
        if tenant is None:
            return None

        # Allow free public or onboarding paths
        for path in self.FREE_PATHS:
            if request.path.startswith(path):
                return None

        # Check subscription
        try:
            sub = TenantSubscription.objects.get(tenant=tenant)
        except TenantSubscription.DoesNotExist:
            return self._block(request, "NO_SUBSCRIPTION")

        # Use correct field name
        if not getattr(sub, "active", False):
            return self._block(request, "INACTIVE_SUBSCRIPTION")

        # Compare dates correctly
        if sub.end_date and sub.end_date < timezone.now().date():
            return self._block(request, "SUBSCRIPTION_EXPIRED")

        return None

    def _block(self, request, reason):
        # API → return JSON error
        if request.path.startswith("/api/"):
            return JsonResponse(
                {"status": "subscription_blocked", "reason": reason},
                status=402,
            )

        # Browser → redirect to subscription selection page
        return redirect("/subscription/select-plan/")