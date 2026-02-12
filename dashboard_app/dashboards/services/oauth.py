# dashboards/oauth/services.py
import requests
import base64
from django.conf import settings
from django.utils import timezone

def refresh_quickbooks_token(api_source):
    """
    Refresh QuickBooks access token using the stored oauth_refresh_token.
    Updates bearer_token and oauth_token_expires_at in the ApiDataSource model.
    """

    if not getattr(api_source, "oauth_refresh_token", None):
        raise ValueError("ApiDataSource missing 'oauth_refresh_token'")

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    # QuickBooks requires Basic Auth with client_id:client_secret
    client_creds = f"{settings.QB_CLIENT_ID}:{settings.QB_CLIENT_SECRET}"
    encoded_creds = base64.b64encode(client_creds.encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded_creds}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": api_source.oauth_refresh_token
    }

    try:
        resp = requests.post(token_url, headers=headers, data=data, timeout=10)
        resp.raise_for_status()
        payload = resp.json()

        # Update ApiDataSource fields
        api_source.bearer_token = payload["access_token"]
        api_source.oauth_refresh_token = payload.get("refresh_token", api_source.oauth_refresh_token)
        api_source.oauth_token_expires_at = timezone.now() + timezone.timedelta(seconds=payload["expires_in"])
        api_source.save(update_fields=["bearer_token", "oauth_refresh_token", "oauth_token_expires_at"])

        return api_source.bearer_token

    except requests.HTTPError as e:
        # Include QuickBooks response for easier debugging
        content = getattr(e.response, "text", str(e))
        raise requests.RequestException(f"Failed to refresh QuickBooks token: {content}") from e
