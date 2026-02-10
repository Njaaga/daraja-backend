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
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")

    if not code or not realm_id:
        logger.warning("QuickBooks callback missing code or realmId")
        return HttpResponse("Invalid callback parameters", status=400)

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
            timeout=10
        )

        if response.status_code != 200:
            logger.error(
                "QuickBooks token request failed: %s - %s",
                response.status_code,
                response.text
            )
            return HttpResponse(
                f"Failed to get QuickBooks token: {response.status_code}", status=500
            )

        data = response.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")

        if not access_token or not refresh_token or not expires_in:
            logger.error("QuickBooks token response missing fields: %s", data)
            return HttpResponse("Invalid token response from QuickBooks", status=500)

        tenant = get_current_tenant()

        ApiDataSource.objects.update_or_create(
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

        return HttpResponse("QuickBooks connected successfully")

    except requests.RequestException as e:
        logger.error("QuickBooks HTTP error: %s", e, exc_info=True)
        return HttpResponse("Failed to communicate with QuickBooks", status=500)

    except Exception as e:
        logger.error("QuickBooks callback error: %s", e, exc_info=True)
        return HttpResponse("An unexpected error occurred", status=500)
