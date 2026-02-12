import requests
from django.conf import settings
from django.utils import timezone


def refresh_quickbooks_token(api_source):
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

    response = requests.post(
        token_url,
        auth=(
            settings.QB_CLIENT_ID,
            settings.QB_CLIENT_SECRET,
        ),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": api_source.oauth_refresh_token,
        },
    )

    response.raise_for_status()
    data = response.json()

    api_source.bearer_token = data["access_token"]
    api_source.refresh_token = data.get(
        "refresh_token", api_source.oauth_refresh_token
    )
    api_source.token_expires_at = (
        timezone.now()
        + timezone.timedelta(seconds=data["expires_in"])
    )
    api_source.save(
        update_fields=[
            "bearer_token",
            "refresh_token",
            "token_expires_at",
        ]
    )
