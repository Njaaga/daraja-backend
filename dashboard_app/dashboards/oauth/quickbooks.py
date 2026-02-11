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
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    state = request.GET.get("state")

    if not code or not state or not realm_id:
        return JsonResponse({"error": "Invalid OAuth response"}, status=400)

    if not state.startswith("tenant:"):
        return JsonResponse({"error": "Invalid state"}, status=400)

    tenant_slug = state.replace("tenant:", "", 1)
    tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()

    if not tenant:
        return JsonResponse({"error": "Tenant not found"}, status=404)

    # 🔑 Exchange code for tokens
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
    )

    token_data = token_response.json()

    if "access_token" not in token_data:
        return JsonResponse(
            {"error": "Token exchange failed", "data": token_data},
            status=400,
        )

    # ✅ Save or update API source
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
            + timezone.timedelta(seconds=token_data.get("expires_in", 3600)),
            "realm_id": realm_id,
        },
    )

    return redirect(f"{settings.FRONTEND_URL}/api-sources?connected=quickbooks")
