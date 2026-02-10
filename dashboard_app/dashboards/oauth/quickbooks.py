import logging
import requests
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils import timezone

from dashboards.models import ApiDataSource
from tenants.utils import get_current_tenant

logger = logging.getLogger(__name__)  # Use Django's logging system


def quickbooks_connect(request):
    """Redirect user to QuickBooks OAuth authorization page."""
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
        logger.exception("QuickBooks connect failed")
        return HttpResponse(f"Error initiating QuickBooks OAuth: {str(e)}", status=500)


def quickbooks_callback(request):
    """Handle QuickBooks OAuth callback and store tokens."""
    try:
        code = request.GET.get("code")
        realm_id = request.GET.get("realmId")

        if not code or not realm_id:
            return HttpResponse("Invalid callback: missing code or realmId", status=400)

        token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

        # Exchange code for access/refresh tokens
        response = requests.post(
            token_url,
            auth=(settings.QUICKBOOKS_CLIENT_ID, settings.QUICKBOOKS_CLIENT_SECRET),
            headers={"Accept": "application/json"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.QUICKBOOKS_REDIRECT_URI,
            },
            timeout=10  # prevent hanging
        )

        if response.status_code != 200:
            logger.error("QuickBooks token exchange failed: %s %s", response.status_code, response.text)
            return HttpResponse(
                f"Failed to exchange code for token. Status: {response.status_code}", status=400
            )

        data = response.json()

        tenant = get_current_tenant()

        # Update or create API data source
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
                "token_expires_at": timezone.now() + timezone.timedelta(seconds=data.get("expires_in", 0)),
            },
        )

        return HttpResponse("QuickBooks connected successfully!")

    except requests.RequestException as e:
        logger.exception("QuickBooks callback HTTP request failed")
        return HttpResponse(f"HTTP request error: {str(e)}", status=500)
    except Exception as e:
        logger.exception("QuickBooks callback processing failed")
        return HttpResponse(f"Internal error: {str(e)}", status=500)
