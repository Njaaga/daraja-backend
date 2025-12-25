from django.db import models
from threading import local
from django.contrib.auth.models import User

# Thread-local storage to keep current tenant
_thread_locals = local()

def get_current_tenant():
    return getattr(_thread_locals, 'tenant', None)

class Tenant(models.Model):
    name = models.CharField(max_length=255)
    subdomain = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    default_payment_method_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name

class TenantUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    is_superadmin = models.BooleanField(default=False)

    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    default_payment_method_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.user.email} - {self.tenant.name}"
