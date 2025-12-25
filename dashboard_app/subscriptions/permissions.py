from rest_framework import permissions
from django.utils import timezone
from tenants.models import TenantUser
from .models import TenantSubscription

class IsTenantSubscribed(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        print("User:", user)
        if not user.is_authenticated:
            print("Not authenticated")
            return False

        tenant_user = TenantUser.objects.filter(user=user).first()
        print("TenantUser:", tenant_user)
        if not tenant_user:
            return False

        tenant = tenant_user.tenant
        print("Tenant:", tenant)
        if not tenant:
            return False

        subscription = getattr(tenant, "tenantsubscription", None)
        print("Subscription:", subscription)
        if not subscription:
            return False

        print("Active:", subscription.active)
        print("End date:", subscription.end_date)

        if not subscription.active:
            return False
        if subscription.end_date and subscription.end_date < timezone.now().date():
            return False

        return True

