# dashboards/oauth/quickbooks.py
import logging
import requests
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils import timezone

from dashboards.models import ApiDataSource
from tenants.utils import get_current_tenant

logger = logging.getLogger(__name__)

def quickbooks_connect(request):
    """Redirect user to QuickBooks OAuth page."""
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
    try:
        code = request.GET.get("code")
        realm_id = request.GET.get("realmId")

        if not code or not realm_id:
            return HttpResponse("Missing code or realmId", status=400)

        tenant = get_current_tenant()
        if not tenant:
            return HttpResponse("No tenant found", status=400)

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

        response.raise_for_status()
        data = response.json()

        # Save/update API datasource
        ApiDataSource.objects.update_or_create(
            tenant=tenant,
            provider="quickbooks",
            defaults={
                "name": "QuickBooks Online",
                "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
                "auth_type": "BEARER",
                "bearer_token": data.get("access_token", ""),
                "refresh_token": data.get("refresh_token", ""),
                "realm_id": realm_id,
                "token_expires_at": timezone.now()
                + timezone.timedelta(seconds=data.get("expires_in", 0)),
            },
        )

        return HttpResponse("QuickBooks connected successfully")

    except requests.RequestException as e:
        # network / HTTP errors
        return HttpResponse(f"Requests error: {str(e)}", status=500)
    except Exception as e:
        # show the full traceback
        tb = traceback.format_exc()
        return HttpResponse(f"Server error:\n{tb}", status=500)
