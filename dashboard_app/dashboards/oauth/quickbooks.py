# dashboards/oauth/quickbooks.py

import requests
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils import timezone
import logging

from dashboards.models import ApiDataSource
from tenants.utils import get_current_tenant

logger = logging.getLogger(__name__)


def quickbooks_connect(request):
    """Redirect user to QuickBooks OAuth page"""
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
    """Handle QuickBooks OAuth callback and save tokens"""
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")

    if not code or not realm_id:
        return HttpResponse("Invalid QuickBooks callback parameters", status=400)

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    try:
        # Ensure env vars exist
        client_id = settings.QUICKBOOKS_CLIENT_ID
        client_secret = settings.QUICKBOOKS_CLIENT_SECRET
        redirect_uri = settings.QUICKBOOKS_REDIRECT_URI

        if not all([client_id, client_secret, redirect_uri]):
            return HttpResponse("QuickBooks credentials not configured", status=500)

        response = requests.post(
            token_url,
            auth=(client_id, client_secret),
            headers={"Accept": "application/json"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            timeout=10,
        )

        try:
            data = response.json()
        except Exception:
            return HttpResponse("Failed to parse QuickBooks token response", status=500)

        if response.status_code != 200:
            logger.error("QuickBooks token error: %s", data)
            return HttpResponse(f"QuickBooks token request failed: {data}", status=400)

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")

        if not access_token or not refresh_token or not expires_in:
            return HttpResponse(f"QuickBooks returned incomplete token data: {data}", status=400)

        tenant = get_current_tenant()

        # Save or update APIDataSource
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

    except requests.RequestException as re:
        logger.exception("HTTP error during QuickBooks token request")
        return HttpResponse(f"HTTP error: {str(re)}", status=500)
    except Exception as e:
        logger.exception("Unexpected error in QuickBooks callback")
        return HttpResponse(f"Server error: {str(e)}", status=500)
