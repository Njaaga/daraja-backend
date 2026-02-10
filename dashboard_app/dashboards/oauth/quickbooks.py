import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone


def quickbooks_connect(request):
    # Normally headers are used to determine tenant
    tenant = request.META.get("HTTP_X_TENANT_SLUG")  # None for redirects
    if not tenant:
        # fallback: extract from query param (frontend must send tenant in ?state=)
        tenant = request.GET.get("state")

    if not tenant:
        return JsonResponse({"error": "Tenant missing"}, status=400)

    url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QUICKBOOKS_CLIENT_ID}"
        "&response_type=code"
        "&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={settings.QUICKBOOKS_REDIRECT_URI}"
        f"&state={tenant}"  # tenant slug passed along
    )
    return redirect(url)



def quickbooks_callback(request):
    from dashboards.models import ApiDataSource
    from tenants.models import Tenant
    import requests
    from django.utils import timezone

    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    state = request.GET.get("state")  # this is the tenant slug

    if not code or not realm_id or not state:
        return JsonResponse({"error": "Invalid callback"}, status=400)

    try:
        tenant = Tenant.objects.get(slug=state)
    except Tenant.DoesNotExist:
        return JsonResponse({"error": "Tenant not found"}, status=400)

    # Exchange code for tokens
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    response = requests.post(
        token_url,
        auth=(settings.QUICKBOOKS_CLIENT_ID, settings.QUICKBOOKS_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.QUICKBOOKS_REDIRECT_URI,
        },
    )

    data = response.json()

    if "access_token" not in data:
        return JsonResponse(
            {"error": "QuickBooks token request failed", "data": data},
            status=400,
        )

    # Save / update the API source for this tenant
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
            "token_expires_at": timezone.now()
            + timezone.timedelta(seconds=data.get("expires_in", 3600)),
        },
    )

    return JsonResponse({"success": True})
