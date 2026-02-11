from urllib.parse import quote
from django.conf import settings
from django.shortcuts import redirect
from django.http import JsonResponse
import requests
from django.utils import timezone
from .models import ApiDataSource
from tenants.models import Tenant

# -----------------------------
# Connect: Redirect to Intuit OAuth
# -----------------------------
def quickbooks_connect(request):
    tenant_slug = request.GET.get("tenant")

    if not tenant_slug:
        return JsonResponse({"error": "Tenant missing"}, status=400)

    state = f"tenant:{tenant_slug}"

    auth_url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QB_CLIENT_ID}"
        "&response_type=code"
        "&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={quote(settings.QB_REDIRECT_URI, safe='')}"
        f"&state={quote(state)}"
    )

    return redirect(auth_url)


# -----------------------------
# Callback: Exchange code for token
# -----------------------------
def quickbooks_callback(request):
    """
    OAuth callback for client-owned QuickBooks accounts.
    Tenant is resolved from OAuth state (NOT headers).
    """

    # -----------------------------
    # 1. Validate OAuth response
    # -----------------------------
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    state = request.GET.get("state")

    if not code or not realm_id or not state:
        return JsonResponse(
            {"error": "Invalid QuickBooks OAuth response"},
            status=400,
        )

    # -----------------------------
    # 2. Extract tenant from state
    # state format: tenant:<slug>
    # -----------------------------
    if not state.startswith("tenant:"):
        return JsonResponse({"error": "Invalid OAuth state"}, status=400)

    tenant_slug = state.replace("tenant:", "", 1)

    tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()
    if not tenant:
        return JsonResponse({"error": "Tenant not found"}, status=404)

    # 🔐 IMPORTANT:
    # Restore tenant context manually for this request
    # (OAuth callbacks do not have headers)
    _thread_locals.tenant = tenant

    # -----------------------------
    # 3. Exchange code for tokens
    # -----------------------------
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    auth_header = base64.b64encode(
        f"{settings.QB_CLIENT_ID}:{settings.QB_CLIENT_SECRET}".encode()
    ).decode()

    token_response = requests.post(
        token_url,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.QB_REDIRECT_URI,
        },
        timeout=15,
    )

    token_data = token_response.json()

    if "access_token" not in token_data:
        return JsonResponse(
            {
                "error": "QuickBooks token exchange failed",
                "details": token_data,
            },
            status=400,
        )

    # -----------------------------
    # 4. Persist ApiDataSource
    # -----------------------------
    expires_in = token_data.get("expires_in", 3600)

    with transaction.atomic():
        ApiDataSource.objects.update_or_create(
            tenant=tenant,
            provider="quickbooks",
            defaults={
                "name": "QuickBooks Online",
                "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
                "auth_type": "OAUTH2",
                "oauth_access_token": token_data["access_token"],
                "oauth_refresh_token": token_data.get("refresh_token"),
                "oauth_token_expires_at": timezone.now()
                + timezone.timedelta(seconds=expires_in),
                "realm_id": realm_id,
                "extra_headers": {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            },
        )

    # -----------------------------
    # 5. Redirect back to frontend
    # -----------------------------
    return redirect(
        f"{settings.FRONTEND_URL}/api-sources?connected=quickbooks"
    )
