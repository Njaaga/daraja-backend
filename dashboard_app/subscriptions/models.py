# subscriptions/models.py
from django.db import models
from django.conf import settings
from tenants.models import Tenant  # adjust import to your tenant app

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="cad")  # e.g., 'usd', 'cad'
    max_users = models.IntegerField(default=5)
    max_groups = models.IntegerField(default=5)
    max_dashboards = models.IntegerField(default=10)
    max_datasets = models.IntegerField(default=10)
    max_api_rows = models.BigIntegerField(default=10000)
    features = models.JSONField(default=dict, blank=True)
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name


# subscriptions/models.py
class TenantSubscription(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE)
    plan = models.ForeignKey('SubscriptionPlan', on_delete=models.SET_NULL, null=True, blank=True)
    active = models.BooleanField(default=False)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    auto_renew = models.BooleanField(default=True)

    # usage
    api_rows_used = models.BigIntegerField(default=0)

    # cached limits
    max_users = models.IntegerField(default=0)
    max_groups = models.IntegerField(default=5)
    max_dashboards = models.IntegerField(default=0)
    max_datasets = models.IntegerField(default=0)
    max_api_rows = models.BigIntegerField(default=0)

    def __str__(self):
        return f"Subscription({self.tenant})"

