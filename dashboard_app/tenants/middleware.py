from threading import local
from .models import Tenant

_thread_locals = local()

def get_current_tenant():
    return getattr(_thread_locals, "tenant", None)


class TenantMiddleware:
    EXEMPT_PATHS = (
        "/api/signup/",
        "/api/login/",
        "/api/token/",
        "/api/subscription/plans/",
        "/admin/",
        "/static/",
        "/media/",
        "/stripe/webhook/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            _thread_locals.tenant = None
            return self.get_response(request)

        # 1️⃣ Header first (ALWAYS)
        subdomain = request.headers.get("X-Tenant-Subdomain")

        # 2️⃣ DEV fallback (explicit only)
        if not subdomain and request.GET.get("tenant"):
            subdomain = request.GET.get("tenant")

        if not subdomain:
            _thread_locals.tenant = None
            return self.get_response(request)

        tenant = Tenant.objects.filter(
            subdomain__iexact=subdomain
        ).first()

        if tenant:
            _thread_locals.tenant = tenant
            print("Tenant detected:", tenant.subdomain)
        else:
            _thread_locals.tenant = None
            print("Tenant NOT found:", subdomain)

        return self.get_response(request)
