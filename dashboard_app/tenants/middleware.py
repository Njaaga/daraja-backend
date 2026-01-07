from threading import local
from django.http import Http404
from .models import Tenant

_thread_locals = local()


def get_current_tenant():
    return getattr(_thread_locals, "tenant", None)


class TenantMiddleware:
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
        "/api/forgot-password",
        "/api/reset-password",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            return self.get_response(request)

        path = request.path.rstrip("/")

        if any(path == p or path.startswith(p + "/") for p in self.EXEMPT_PREFIXES):
            _thread_locals.tenant = None
            return self.get_response(request)

        tenant_slug = request.META.get("HTTP_X_TENANT_SLUG")

        if not tenant_slug:
            raise Http404("Tenant header missing")

        tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()
        if not tenant:
            raise Http404(f"Tenant '{tenant_slug}' not found")

        _thread_locals.tenant = tenant
        return self.get_response(request)

