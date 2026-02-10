import requests
from django.utils import timezone
from dashboards.services.oauth import refresh_quickbooks_token


def execute_request(api_source, endpoint, method="GET", params=None, body=None):
    if (
        api_source.provider == "quickbooks"
        and api_source.token_expires_at
        and api_source.token_expires_at <= timezone.now()
    ):
        refresh_quickbooks_token(api_source)

    headers = {}

    if api_source.auth_type == "API_KEY_HEADER":
        headers[api_source.api_key_name] = api_source.api_key

    if api_source.auth_type == "BEARER":
        headers["Authorization"] = f"Bearer {api_source.bearer_token}"

    url = f"{api_source.base_url}/{endpoint.lstrip('/')}"

    response = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=body,
    )

    response.raise_for_status()
    return response.json()
