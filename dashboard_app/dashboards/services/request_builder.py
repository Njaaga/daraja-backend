import logging
import requests
from django.utils import timezone
from dashboards.oauth.services import refresh_quickbooks_token

logger = logging.getLogger(__name__)


def execute_request(api_source, endpoint, method="GET", params=None, body=None):
    """
    Execute API request safely.
    Auto-refresh QuickBooks token if expired.
    """
    try:
        # Refresh QuickBooks token if needed
        if (
            api_source.provider == "quickbooks"
            and api_source.token_expires_at
            and api_source.token_expires_at <= timezone.now()
        ):
            logger.info("Refreshing QuickBooks token for %s", api_source)
            refresh_quickbooks_token(api_source)

        headers = {}

        if api_source.auth_type == "API_KEY_HEADER":
            headers[api_source.api_key_name] = api_source.api_key

        if api_source.auth_type == "BEARER":
            headers["Authorization"] = f"Bearer {api_source.bearer_token}"

        url = f"{api_source.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        response = requests.request(
            method, url, headers=headers, params=params, json=body, timeout=10
        )

        response.raise_for_status()
        return response.json()

    except requests.HTTPError as e:
        logger.error("API request failed: %s %s", e.response.status_code, e.response.text)
        raise
    except requests.RequestException as e:
        logger.exception("Network error during API request")
        raise
    except Exception as e:
        logger.exception("Unexpected error during API request")
        raise
