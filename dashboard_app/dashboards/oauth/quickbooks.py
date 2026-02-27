# dashboards/oauth/quickbooks.py
from urllib.parse import quote
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse
import requests
from django.utils import timezone
from dashboards.models import ApiDataSource
from tenants.models import Tenant

# -----------------------------
# Connect: Redirect to Intuit OAuth
# -----------------------------
def quickbooks_connect(request):
    tenant_slug = request.GET.get("tenant")

    if not tenant_slug:
        return JsonResponse({"error": "Tenant missing"}, status=400)

    # Encode redirect_uri and state
    redirect_uri = quote(settings.QB_REDIRECT_URI, safe="")
    state = quote(f"tenant:{tenant_slug}", safe="")

    auth_url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QB_CLIENT_ID}"
        f"&response_type=code"
        f"&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )

    return redirect(auth_url)


# -----------------------------
# Callback: Exchange code for token and save
# -----------------------------
def quickbooks_callback(request):
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    state = request.GET.get("state")

    if not code or not state:
        return JsonResponse({"error": "Invalid OAuth response"}, status=400)

    # Extract tenant slug from state
    if not state.startswith("tenant:"):
        return JsonResponse({"error": "Invalid state"}, status=400)

    tenant_slug = state.replace("tenant:", "", 1)
    tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()
    if not tenant:
        return JsonResponse({"error": "Tenant not found"}, status=404)

    # Exchange code for access token
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    try:
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
    except Exception as e:
        return JsonResponse({"error": "Failed to get QuickBooks token", "details": str(e)}, status=500)

    if "access_token" not in data:
        return JsonResponse({"error": "QuickBooks token exchange failed", "data": data}, status=400)

    access_token = data["access_token"]
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in", 3600)

    # Save or update QuickBooks API source for this tenant
    api_source, created = ApiDataSource.objects.update_or_create(
        tenant=tenant,
        provider="quickbooks",
        defaults={
            "name": "QuickBooks Online",
            "base_url": f"https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}",
            "auth_type": "BEARER",
            "bearer_token": access_token,
            "oauth_refresh_token": refresh_token,
            "realm_id": realm_id,
            "oauth_token_expires_at": timezone.now() + timezone.timedelta(seconds=expires_in),
        },
    )

    # Redirect to frontend
    return redirect(f"{settings.FRONTEND_URL}/api-sources?qb_connected=1")
