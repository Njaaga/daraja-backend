import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from urllib.parse import quote



def quickbooks_connect(request):
    tenant_slug = request.GET.get("state")  # tenant passed from frontend
    if not tenant_slug:
        return JsonResponse({"error": "Tenant missing"}, status=400)

    redirect_uri = quote(settings.QB_REDIRECT_URI, safe="")

    url = (
        f"https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QB_CLIENT_ID}"
        f"&response_type=code"
        f"&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={redirect_uri}"
        f"&state={tenant_slug}"
    )
    return redirect(url)



def quickbooks_callback(request):
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    tenant_slug = request.GET.get("state")  # passed via state

    if not code or not realm_id or not tenant_slug:
        return JsonResponse({"error": "Invalid callback"}, status=400)

    try:
        tenant = Tenant.objects.get(subdomain__iexact=tenant_slug)
    except Tenant.DoesNotExist:
        return JsonResponse({"error": "Tenant not found"}, status=400)

    # Exchange code for tokens
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
        return JsonResponse({"error": "QuickBooks token request failed", "data": data}, status=400)

    # Save / update API source
    ApiDataSource.objects.update_or_create(
        tenant=tenant,
        provider="quickbooks",
        defaults={
            "name": "QuickBooks Online",
            "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
            "auth_type": "BEARER",
            "bearer_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "realm_id": realm_id,
            "token_expires_at": timezone.now() + timezone.timedelta(seconds=data.get("expires_in", 3600)),
        },
    )

    return JsonResponse({"success": True})
