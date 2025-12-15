# subscriptions/admin.py
from django.contrib import admin
from .models import SubscriptionPlan, TenantSubscription

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "max_users", "max_dashboards", "max_datasets", "max_api_rows")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("price", "max_users", "max_dashboards", "max_datasets", "max_api_rows")
    search_fields = ("name", "slug")

@admin.register(TenantSubscription)
class TenantSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "active", "auto_renew", "start_date", "end_date")
    readonly_fields = ("max_users", "max_dashboards", "max_datasets", "max_api_rows")
    search_fields = ("tenant__subdomain", "tenant__name")
