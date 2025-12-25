from threading import local
from django.http import Http404
from .models import Tenant

_thread_locals = local()


def get_current_tenant():
    return getattr(_thread_locals, "tenant", None)


class TenantMiddleware:
    """
    Header-based multitenancy middleware
    """

    EXEMPT_PREFIXES = (
        "/api/tenants/login",
        "/api/tenants/signup",
        "/api/tenants/verify-email",
        "/api/token",
        "/api/token/refresh",
        "/api/subscription/plans",
        "/api/subscription/stripe-webhook",
        "/admin",
        "/static",
        "/media",
        "/stripe/webhook",
        "/api/forgot-password",
        "/api/reset-password",
    )

    TENANT_HEADER = "HTTP_X_TENANT_SLUG"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # -------------------------------
        # Allow CORS preflight
        # -------------------------------
        if request.method == "OPTIONS":
            return self.get_response(request)

        # -------------------------------
        # Normalize path
        # -------------------------------
        path = request.path.rstrip("/")

        # DEBUG (temporary – keep this for now)
        print("🔎 Incoming path:", path)

        # -------------------------------
        # Exempt paths
        # -------------------------------
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            _thread_locals.tenant = None
            return self.get_response(request)

        # -------------------------------
        # Tenant resolution
        # -------------------------------
        tenant_slug = request.META.get(self.TENANT_HEADER)

        if not tenant_slug:
            raise Http404("Tenant header missing")

        # ✅ Use 'subdomain' instead of 'slug'
        tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()
        if not tenant:
            raise Http404(f"Tenant '{tenant_slug}' not found")

        _thread_locals.tenant = tenant
        return self.get_response(request)

