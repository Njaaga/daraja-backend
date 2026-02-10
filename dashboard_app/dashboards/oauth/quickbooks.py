# dashboards/oauth/quickbooks.py
import requests
import traceback
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from dashboards.models import ApiDataSource
from tenants.utils import get_current_tenant


def quickbooks_connect(request):
    url = (
        "https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={settings.QUICKBOOKS_CLIENT_ID}"
        "&response_type=code"
        "&scope=com.intuit.quickbooks.accounting"
        f"&redirect_uri={settings.QUICKBOOKS_REDIRECT_URI}"
        "&state=secure"
    )
    return redirect(url)


def quickbooks_callback(request):
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")

    if not code or not realm_id:
        return JsonResponse({"error": "Invalid callback"}, status=400)

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    try:
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
            # Debugging: return QuickBooks response
            return JsonResponse({"error": "QuickBooks token request failed", "data": data}, status=400)

        tenant = get_current_tenant()

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

        return JsonResponse({"success": True, "message": "QuickBooks connected successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
