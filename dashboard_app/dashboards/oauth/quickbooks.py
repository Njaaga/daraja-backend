from urllib.parse import quote
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse
import requests
from django.utils import timezone
from dashboards.models import ApiDataSource
from tenants.middleware import get_current_tenant

# -----------------------------
# Connect: Redirect to Intuit OAuth
# -----------------------------
def quickbooks_connect(request):
    tenant_slug = request.GET.get("state")
    if not tenant_slug:
        return JsonResponse({"error": "Tenant state missing"}, status=400)

    redirect_uri = quote(settings.QB_REDIRECT_URI, safe="")

    url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QB_CLIENT_ID}"
        "&response_type=code"
        "&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={redirect_uri}"
        f"&state={tenant_slug}"
    )
    return redirect(url)


# -----------------------------
# Callback: Exchange code for token
# -----------------------------
def quickbooks_callback(request):
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    tenant_slug = request.GET.get("state")

    if not code or not realm_id or not tenant_slug:
        return JsonResponse({"error": "Invalid callback"}, status=400)

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    response = requests.post(
        token_url,
        auth=(settings.QB_CLIENT_ID, settings.QB_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.QB_REDIRECT_URI,
        },
    )
    data = response.json()
    if "access_token" not in data:
        return JsonResponse({"error": "QuickBooks token failed", "data": data}, status=400)

    # Find tenant object by slug
    from tenants.models import Tenant
    tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()
    if not tenant:
        return JsonResponse({"error": f"Tenant '{tenant_slug}' not found"}, status=404)

    # Save or update the QuickBooks API source for this tenant
    ApiDataSource.objects.update_or_create(
        tenant=tenant,
        provider="quickbooks",
        defaults={
            "name": "QuickBooks Online",
            "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
            "auth_type": "BEARER",
            "bearer_token": data["access_token"],
            "oauth_refresh_token": data.get("refresh_token"),
            "realm_id": realm_id,
            "oauth_token_expires_at": timezone.now() + timezone.timedelta(seconds=data.get("expires_in", 3600)),
        },
    )

    # Optionally redirect to frontend dashboard
    from django.shortcuts import redirect as dj_redirect
    return dj_redirect(f"{settings.FRONTEND_URL}/api-sources?qb_connected=1")
