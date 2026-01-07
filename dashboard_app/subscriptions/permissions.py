from rest_framework import permissions
from django.utils import timezone
from tenants.models import TenantUser
from subscriptions.models import TenantSubscription

class IsTenantSubscribed(permissions.BasePermission):
    message = "Active subscription required."

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        tenant_user = TenantUser.objects.filter(user=user).select_related("tenant").first()
        if not tenant_user:
            return False

        tenant = tenant_user.tenant
        if not tenant:
            return False

        subscription = (
            TenantSubscription.objects
            .filter(tenant=tenant, active=True)
            .order_by("-end_date")
            .first()
        )

        if not subscription:
            return False

        if subscription.end_date and subscription.end_date < timezone.now().date():
            return False

        return True
