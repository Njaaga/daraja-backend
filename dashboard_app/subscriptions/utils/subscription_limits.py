from tenants.middleware import get_current_tenant
from subscriptions.models import SubscriptionPlan, TenantSubscription
from django.utils import timezone


def get_active_subscription():
    tenant = get_current_tenant()
    if not tenant:
        return None
    
    try:
        sub = TenantSubscription.objects.get(tenant=tenant)
        if sub.active and (not sub.end_date or sub.end_date >= timezone.now().date()):
            return sub
        return None
    except TenantSubscription.DoesNotExist:
        return None


def has_reached_limit(count, limit):
    if limit is None:
        return False  # unlimited
    return count >= limit
