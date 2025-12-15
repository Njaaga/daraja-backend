# subscriptions/serializers.py
from rest_framework import serializers
from .models import SubscriptionPlan, TenantSubscription

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "slug", "price", "max_users", "max_dashboards", "max_datasets", "max_api_rows", "features"]

class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer()
    class Meta:
        model = TenantSubscription
        fields = ["tenant", "plan", "active", "start_date", "end_date", "metadata"]
