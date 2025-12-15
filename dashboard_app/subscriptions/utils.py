# subscriptions/utils.py
from django.utils import timezone
from decimal import Decimal

def apply_plan_limits_to_subscription(subscription):
    """Copy plan limits into the subscription and save."""
    plan = subscription.plan
    if not plan:
        return
    subscription.max_users = plan.max_users
    subscription.max_dashboards = plan.max_dashboards
    subscription.max_datasets = plan.max_datasets
    subscription.max_api_rows = plan.max_api_rows
    subscription.save(update_fields=[
        "max_users","max_dashboards","max_datasets","max_api_rows"
    ])

def prorate_and_switch_plan(subscription, new_plan):
    """
    Basic prorate: if subscription.active and has remaining days,
    compute simple prorate credit and extend end_date accordingly OR set new limits immediately.
    (This is a basic approach — adapt to your billing/stripe setup.)
    """
    now = timezone.now()
    # If no active or no end_date: apply immediately
    if not subscription.active or not subscription.end_date:
        subscription.plan = new_plan
        apply_plan_limits_to_subscription(subscription)
        subscription.save()
        return subscription

    # Compute remaining days credit ratio
    remaining = (subscription.end_date - now).total_seconds()
    total_period = (subscription.end_date - subscription.start_date).total_seconds() if subscription.start_date else None
    credit_ratio = 0
    if total_period and total_period > 0:
        credit_ratio = max(0, remaining / total_period)

    # monetary prorate example (requires SubscriptionPlan.price Decimal)
    old_price = subscription.plan.price or Decimal("0.00")
    new_price = new_plan.price or Decimal("0.00")
    credit_amount = (old_price * Decimal(credit_ratio)).quantize(Decimal("0.01"))

    # You would now create invoice/charge logic with Stripe: charge (new_price - credit_amount) etc.
    # For now we simply switch plan and apply new limits (you can add payment handling separately).
    subscription.plan = new_plan
    apply_plan_limits_to_subscription(subscription)
    subscription.start_date = now
    subscription.end_date = now + timezone.timedelta(days=30)  # reset period; adapt as needed
    subscription.save()
    return subscription
