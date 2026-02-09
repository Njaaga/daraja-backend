import requests
from django.conf import settings
from django.utils import timezone


def refresh_quickbooks_token(api_source):
    response = requests.post(
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        auth=(
            settings.QUICKBOOKS_CLIENT_ID,
            settings.QUICKBOOKS_CLIENT_SECRET,
        ),
        data={
            "grant_type": "refresh_token",
            "refresh_token": api_source.refresh_token,
        },
    )

    data = response.json()

    api_source.bearer_token = data["access_token"]
    api_source.refresh_token = data.get(
        "refresh_token", api_source.refresh_token
    )
    api_source.token_expires_at = timezone.now() + timezone.timedelta(
        seconds=data["expires_in"]
    )
    api_source.save()
