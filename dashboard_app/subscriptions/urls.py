# subscriptions/urls.py
from django.urls import path
from . import views


urlpatterns = [
    # Plans
    path("plans/", views.ListPlansView.as_view(), name="list-plans"),

    # Stripe Checkout
    path("create-checkout-session/", views.CreateStripeCheckoutSession.as_view(), name="create-checkout-session"),
    path("stripe-confirm-payment/", views.StripeConfirmPayment.as_view(), name="stripe-confirm-payment"),

    # Subscription status
    path("status/", views.SubscriptionStatusView.as_view(), name="subscription-status"),

    # Cancel / Auto-renew
    path("cancel-subscription/", views.CancelSubscriptionView.as_view(), name="cancel-subscription"),
    path("toggle-auto-renew/", views.ToggleAutoRenewView.as_view(), name="toggle-auto-renew"),

    # Invoices
    path("list-invoices/", views.ListInvoicesView.as_view(), name="list-invoices"),

    # Payment methods
    path("create-setup-intent/", views.CreateSetupIntentView.as_view(), name="create-setup-intent"),
    path("list-payment-methods/", views.ListPaymentMethods.as_view(), name="list-payment-methods"),
    path("set-default-payment-method/", views.SetDefaultPaymentMethod.as_view(), name="set-default-payment-method"),

    # Stripe webhook
    path("stripe-webhook/", views.stripe_webhook, name="stripe-webhook"),

    path("change-plan/", views.CreateSubscriptionWithSavedCardView.as_view(), name="change-plan"),

    path("delete-payment-method/", views.DeletePaymentMethod.as_view(), name="delete-payment-method"),
]
