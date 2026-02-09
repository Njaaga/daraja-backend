import requests
from django.utils import timezone
from .oauth import refresh_quickbooks_token


def build_headers(source):
    headers = {"Accept": "application/json"}

    if source.provider == "quickbooks":
        if source.token_expired():
            refresh_quickbooks_token(source)

        headers["Authorization"] = f"Bearer {source.oauth_access_token}"

    elif source.auth_type == "API_KEY_HEADER":
        headers[source.api_key_name] = source.api_key

    elif source.auth_type == "BEARER":
        headers["Authorization"] = (
            f"{source.bearer_prefix} {source.bearer_token}"
        )

    headers.update(source.extra_headers or {})
    return headers


def execute_dataset(source, dataset):
    base_url = source.base_url.replace(
        "{realm_id}", source.realm_id or ""
    )

    url = f"{base_url}{dataset.endpoint}"

    response = requests.get(
        url,
        headers=build_headers(source),
        params=dataset.query_params,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()

