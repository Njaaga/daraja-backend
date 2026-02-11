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
        f"&response_type=code"
        f"&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={quote(settings.QB_REDIRECT_URI)}"
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

    if not code or not state:
        return JsonResponse({"error": "Invalid OAuth response"}, status=400)

    # ✅ Extract tenant safely
    if not state.startswith("tenant:"):
        return JsonResponse({"error": "Invalid state"}, status=400)

    tenant_slug = state.replace("tenant:", "", 1)
    tenant = Tenant.objects.filter(subdomain=tenant_slug).first()

    if not tenant:
        return JsonResponse({"error": "Tenant not found"}, status=404)

    # ⬇️ Now you have tenant WITHOUT headers
    ApiSource.objects.create(
        tenant=tenant,
        type="quickbooks",
        realm_id=realm_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    return redirect(f"{settings.FRONTEND_URL}/api-sources?connected=quickbooks")
