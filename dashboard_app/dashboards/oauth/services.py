import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


def refresh_quickbooks_token(source):
    if not source.oauth_refresh_token:
        raise Exception("Missing refresh token")

    res = requests.post(
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        auth=(settings.QB_CLIENT_ID, settings.QB_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": source.oauth_refresh_token,
        },
    ).json()

    source.oauth_access_token = res["access_token"]
    source.oauth_refresh_token = res["refresh_token"]
    source.oauth_token_expires_at = timezone.now() + timedelta(
        seconds=res["expires_in"]
    )
    source.save()

    return source.oauth_access_token

