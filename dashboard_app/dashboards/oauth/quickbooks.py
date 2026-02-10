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
    """Handle QuickBooks OAuth callback and store tokens."""
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")

    logger.info("QuickBooks callback received: code=%s, realmId=%s", code, realm_id)

    if not code or not realm_id:
        logger.error("Missing code or realmId in callback")
        return HttpResponse("Invalid callback", status=400)

    tenant = get_current_tenant()
    if tenant is None:
        logger.error("No tenant found in callback")
        return HttpResponse("No tenant found", status=400)

    # Exchange code for tokens
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    auth = (settings.QUICKBOOKS_CLIENT_ID, settings.QUICKBOOKS_CLIENT_SECRET)
    headers = {"Accept": "application/json"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.QUICKBOOKS_REDIRECT_URI,
    }

    try:
        response = requests.post(token_url, auth=auth, headers=headers, data=data)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.exception("Error exchanging code for token: %s", e)
        return HttpResponse("Error retrieving tokens from QuickBooks", status=500)

    try:
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        if not access_token or not refresh_token:
            logger.error("Incomplete token data received: %s", token_data)
            return HttpResponse("Incomplete token data from QuickBooks", status=500)

        # Save/update API datasource
        obj, created = ApiDataSource.objects.update_or_create(
            tenant=tenant,
            provider="quickbooks",
            defaults={
                "name": "QuickBooks Online",
                "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
                "auth_type": "BEARER",
                "bearer_token": access_token,
                "refresh_token": refresh_token,
                "realm_id": realm_id,
                "token_expires_at": timezone.now() + timezone.timedelta(seconds=expires_in),
            },
        )
        logger.info("QuickBooks API source saved: %s", obj)
    except Exception as e:
        logger.exception("Error saving API datasource")
        return HttpResponse("Error saving API datasource", status=500)

    return HttpResponse("QuickBooks connected successfully")
