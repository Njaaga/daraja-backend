import logging
import requests
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils import timezone

from dashboards.models import ApiDataSource
from tenants.utils import get_current_tenant

logger = logging.getLogger(__name__)

# -----------------------------------------------------------
# Step 1: Redirect user to QuickBooks OAuth page
# -----------------------------------------------------------
def quickbooks_connect(request):
    try:
        url = (
            "https://appcenter.intuit.com/connect/oauth2"
            f"?client_id={settings.QUICKBOOKS_CLIENT_ID}"
            "&response_type=code"
            "&scope=com.intuit.quickbooks.accounting"
            f"&redirect_uri={settings.QUICKBOOKS_REDIRECT_URI}"
            "&state=secure"
        )
        return redirect(url)
    except Exception as e:
        logger.error("QuickBooks connect error: %s", e, exc_info=True)
        return HttpResponse("Failed to initiate QuickBooks OAuth.", status=500)


# -----------------------------------------------------------
# Step 2: Handle OAuth callback
# -----------------------------------------------------------
def quickbooks_callback(request):
    logger.info("QuickBooks callback reached with GET params: %s", request.GET)

    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")

    if not code or not realm_id:
        logger.error("Missing code or realmId in callback")
        return HttpResponse("Invalid callback", status=400)

    tenant = get_current_tenant()
    if tenant is None:
        logger.error("No tenant found in callback")
        return HttpResponse("No tenant", status=400)

    # Temporarily skip real token request for testing
    try:
        obj, created = ApiDataSource.objects.update_or_create(
            tenant=tenant,
            provider="quickbooks",
            defaults={
                "name": "QuickBooks Online",
                "base_url": f"https://quickbooks.api.intuit.com/v3/company/{realm_id}",
                "auth_type": "BEARER",
                # Dummy tokens for now
                "bearer_token": "dummy",
                "refresh_token": "dummy",
                "realm_id": realm_id,
                "token_expires_at": timezone.now() + timezone.timedelta(hours=1),
            }
        )
        logger.info("API datasource saved: %s", obj)
    except Exception as e:
        logger.exception("Error saving API datasource")
        return HttpResponse("Server error", status=500)

    return HttpResponse("QuickBooks connected successfully")
