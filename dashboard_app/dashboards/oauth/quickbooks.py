import requests
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils import timezone

from api_sources.models import ApiDataSource
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
        return HttpResponse("Invalid callback", status=400)

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    response = requests.post(
        token_url,
        auth=(
            settings.QUICKBOOKS_CLIENT_ID,
            settings.QUICKBOOKS_CLIENT_SECRET,
        ),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.QUICKBOOKS_REDIRECT_URI,
        },
    )

    data = response.json()

    tenant = get_current_tenant()

    ApiDataSource.objects.update_or_create(
        tenant=tenant,
        provider="quickbooks",
        defaults={
            "name": "QuickBooks Online",
            "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
            "auth_type": "BEARER",
            "bearer_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "realm_id": realm_id,
            "token_expires_at": timezone.now()
            + timezone.timedelta(seconds=data["expires_in"]),
        },
    )

    return HttpResponse("QuickBooks connected successfully")
