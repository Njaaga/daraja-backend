from rest_framework.exceptions import PermissionDenied

from subscriptions.models import TenantSubscription
from dashboards.models import ApiDataSource
from dashboards.models import Dataset
from dashboards.models import Dashboard
from dashboards.models import Group
from tenants.models import TenantUser
from django.contrib.auth import get_user_model

User = get_user_model()


RESOURCE_MAP = {
    "datasources": {
        "model": ApiDataSource,
        "field": "max_api_rows",
        "label": "datasources",
    },

    "datasets": {
        "model": Dataset,
        "field": "max_datasets",
        "label": "datasets",
    },

    "dashboards": {
        "model": Dashboard,
        "field": "max_dashboards",
        "label": "dashboards",
    },
    "users": {
        "model": TenantUser,
        "field": "max_users",
        "label": "users",
    },
        "groups": {
        "model": Group,
        "field": "max_groups",
        "label": "groups",
    },
}


def enforce_subscription_limit(tenant, resource: str):
    """
    Generic subscription limit enforcement.

    resource:
        - 'datasources'
        - 'datasets'
        - 'dashboards'
        - 'users'
    """

    config = RESOURCE_MAP.get(resource)
    if not config:
        raise ValueError(f"Unknown subscription resource: {resource}")

    sub = (
        TenantSubscription.objects
        .filter(tenant=tenant, active=True)
        .select_related("plan")
        .first()
    )

    if not sub:
        raise PermissionDenied("No active subscription.")

    limit = getattr(sub, config["field"])

    # Unlimited
    if limit is None:
        return

    current_count = config["model"].objects.filter(tenant=tenant).count()

    if current_count >= limit:
        raise PermissionDenied(
            f"{config['label'].capitalize()} limit reached "
            f"({limit}). Please upgrade your plan."
        )
