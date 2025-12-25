# subscriptions/views.py
from django.shortcuts import get_object_or_404
import logging
import stripe
from django.db import transaction
from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from tenants.middleware import get_current_tenant
from .models import SubscriptionPlan, TenantSubscription
from tenants.models import Tenant, TenantUser
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from datetime import datetime, timedelta, timezone as dt_timezone
from django.db import transaction
from django.utils.timezone import localtime

logger = logging.getLogger(__name__)


stripe.api_key = settings.STRIPE_SECRET_KEY
FRONTEND_URL = settings.FRONTEND_URL


class ListPlansView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.all().values("id", "name", "price")
        return Response(plans)

class CreateStripeCheckoutSession(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        print("=== Incoming Request ===")
        print("Headers:", request.headers)
        print("Body:", request.data)

        # Get tenant from header
        tenant_slug = request.META.get("HTTP_X_TENANT_SLUG")
        if not tenant_slug:
            print("❌ Tenant header missing")
            return Response({"error": "Tenant header missing"}, status=400)
        print(f"✅ Tenant header found: {tenant_slug}")

        tenant = get_object_or_404(Tenant, subdomain=tenant_slug)
        print(f"✅ Tenant detected: {tenant}")

        # Get plan
        plan_id = request.data.get("plan_id")
        if not plan_id:
            print("❌ Plan ID missing")
            return Response({"error": "Plan ID missing"}, status=400)
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        print(f"✅ Plan found: {plan.name} (${plan.price})")

        # Get superadmin user
        tenant_user = TenantUser.objects.filter(tenant=tenant, is_superadmin=True).first()
        if not tenant_user:
            print(f"❌ No superadmin user found for tenant {tenant_slug}")
            return Response({"error": "No superadmin user found for tenant"}, status=400)
        customer_email = tenant_user.user.email
        print(f"✅ Superadmin email: {customer_email}")

        # Create or retrieve Stripe customer
        if tenant.stripe_customer_id:
            try:
                customer = stripe.Customer.retrieve(tenant.stripe_customer_id)
                print(f"✅ Using existing Stripe customer: {customer.id}")
            except Exception:
                customer = stripe.Customer.create(email=customer_email, metadata={"tenant_slug": tenant_slug})
                tenant.stripe_customer_id = customer.id
                tenant.save()
                print(f"✅ Created new Stripe customer: {customer.id}")
        else:
            customer = stripe.Customer.create(email=customer_email, metadata={"tenant_slug": tenant_slug})
            tenant.stripe_customer_id = customer.id
            tenant.save()
            print(f"✅ Created Stripe customer: {customer.id}")

        # Create checkout session
        try:
            session = stripe.checkout.Session.create(
                customer=customer.id,
                mode="subscription",
                payment_method_types=["card"],
                line_items=[{
                    "price": plan.stripe_price_id,
                    "quantity": 1,
                }],
                subscription_data={
                    "metadata": {
                        "tenant_slug": tenant_slug,
                        "plan_id": str(plan.id),
                    }
                },
                success_url=f"{settings.FRONTEND_URL}/billing?success=1",
                cancel_url=f"{settings.FRONTEND_URL}/billing?canceled=1",
            )
            print(f"✅ Checkout session created: {session.id}")
            return Response({"url": session.url})
        except Exception as e:
            print(f"❌ Stripe error creating session: {e}")
            return Response({"error": str(e)}, status=400)




@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=endpoint_secret
        )
    except ValueError:
        logger.error("Invalid payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.error("Invalid signature")
        return HttpResponse(status=400)

    try:
        event_type = event["type"]
        data_object = event["data"]["object"]

        # Handle creation and updates
        if event_type in ["customer.subscription.created", "customer.subscription.updated"]:
            items = data_object.get("items", {}).get("data", [])
            if not items:
                logger.warning("No subscription items found.")
                return HttpResponse(status=200)

            subscription_item = items[0]
            start_ts = subscription_item.get("current_period_start")
            end_ts = subscription_item.get("current_period_end")

            start_date = datetime.fromtimestamp(start_ts, tz=dt_timezone.utc) if start_ts else None
            end_date = datetime.fromtimestamp(end_ts, tz=dt_timezone.utc) if end_ts else None

            # Resolve tenant and plan from metadata
            tenant_slug = data_object.get("metadata", {}).get("tenant_slug")
            plan_id = data_object.get("metadata", {}).get("plan_id")
            if not tenant_slug:
                logger.error("Tenant slug missing in subscription metadata")
                return HttpResponse(status=400)

            tenant = Tenant.objects.filter(subdomain__iexact=tenant_slug).first()
            if not tenant:
                logger.error(f"Tenant '{tenant_slug}' not found")
                return HttpResponse(status=400)

            plan = SubscriptionPlan.objects.filter(id=plan_id).first() if plan_id else None

            # Update or create subscription in DB
            sub, created = TenantSubscription.objects.update_or_create(
                tenant=tenant,
                defaults={
                    "plan": plan,
                    "stripe_subscription_id": data_object["id"],
                    "start_date": start_date,
                    "end_date": end_date,
                    # Only active if Stripe status is 'active' and not set to cancel at period end
                    "active": data_object['status'] == 'active' and not data_object.get("cancel_at_period_end", False),
                    "auto_renew": not data_object.get("cancel_at_period_end", False),
                    "max_api_rows": plan.max_api_rows,
                    "max_dashboards": plan.max_dashboards,
                    "max_datasets": plan.max_datasets,
                    "max_users": plan.max_users,
                    "max_groups": plan.max_groups,
                }
            )

            logger.info(
                f"Subscription {'created' if created else 'updated'} for tenant {tenant_slug}, "
                f"active={sub.active}, auto_renew={sub.auto_renew}, period: {start_date} - {end_date}"
            )

        elif event_type == "invoice.paid":
            subscription_id = data_object.get("subscription")
            if subscription_id:
                sub = TenantSubscription.objects.filter(stripe_subscription_id=subscription_id).first()
                if sub:
                    sub.active = True
                    sub.save()
                    logger.info(f"Invoice paid, subscription {subscription_id} marked active")
            else:
                logger.warning("Invoice does not have a subscription ID.")

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return HttpResponse(status=200)

    return HttpResponse(status=200)




@method_decorator(csrf_exempt, name="dispatch")
class StripeConfirmPayment(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        session_id = request.data.get("session_id")
        tenant_subdomain = request.data.get("tenant_subdomain")
        if not session_id or not tenant_subdomain:
            return Response({"error": "Missing session_id or tenant_subdomain"}, status=400)

        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.InvalidRequestError:
            return Response({"error": "Invalid Stripe session ID."}, status=400)

        try:
            tenant = Tenant.objects.get(subdomain=tenant_subdomain)
            sub = TenantSubscription.objects.filter(tenant=tenant).first()
            if sub:
                plan = sub.plan
                return Response({
                    "status": "success",
                    "current_plan": {
                        "id": plan.id if plan else None,
                        "name": plan.name if plan else None,
                        "price": plan.price if plan else None,
                        "start_date": sub.start_date,
                        "end_date": sub.end_date,
                        "active": sub.active,
                        "auto_renew": sub.auto_renew,
                        "max_users": sub.max_users,
                        "max_dashboards": sub.max_dashboards,
                        "max_datasets": sub.max_datasets,
                        "max_api_rows": sub.max_api_rows,
                    }
                })
        except Tenant.DoesNotExist:
            return Response({"error": "Tenant not found."}, status=404)

        return Response({"status": "pending"})


class SubscriptionStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            tenant_user = TenantUser.objects.select_related("tenant").get(user=request.user)
            tenant = tenant_user.tenant
        except TenantUser.DoesNotExist:
            return Response({"active": False})

        sub = TenantSubscription.objects.select_related("plan").filter(tenant=tenant).first()
        if not sub:
            return Response({"active": False})

        # Format dates
        start_str = localtime(sub.start_date).strftime("%m/%d/%Y") if sub.start_date else None
        end_str = sub.end_date.strftime("%m/%d/%Y") if sub.end_date else None

        return Response({
            "current_plan": {
                "id": sub.plan.id if sub.plan else None,
                "name": sub.plan.name if sub.plan else None,
                "price": sub.plan.price if sub.plan else None,
                "start_date": start_str,
                "end_date": end_str,
                "auto_renew": sub.auto_renew,
                "active": sub.active,
            }
        })




class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=404)

        try:
            sub = TenantSubscription.objects.get(tenant=tenant)
        except TenantSubscription.DoesNotExist:
            return Response({"error": "No subscription found to cancel."}, status=404)

        if sub.stripe_subscription_id:
            try:
                # Retrieve current Stripe subscription
                stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
                status = stripe_sub.status

                if status in ['active', 'trialing']:
                    # Cancel at period end
                    stripe.Subscription.modify(
                        sub.stripe_subscription_id,
                        cancel_at_period_end=True
                    )
                    sub.auto_renew = False
                    sub.save()
                    return Response({
                        "status": "success",
                        "message": "Subscription will be canceled at the end of the current period."
                    })
                else:
                    # Subscription not active; mark inactive immediately
                    sub.active = False
                    sub.auto_renew = False
                    sub.end_date = timezone.now()
                    sub.save()
                    return Response({
                        "status": "success",
                        "message": f"Subscription is {status}, canceled locally."
                    })

            except stripe.error.StripeError as e:
                print("🔥 Stripe error:", e)
                return Response({"error": f"Stripe error: {str(e)}"}, status=500)
            except Exception as e:
                print("🔥 Cancel subscription error:", e)
                return Response({"error": str(e)}, status=500)
        else:
            # No Stripe subscription ID, cancel locally
            sub.active = False
            sub.auto_renew = False
            sub.end_date = timezone.now()
            sub.save()
            return Response({
                "status": "success",
                "message": "Subscription canceled locally."
            })
        

class ToggleAutoRenewView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=404)
        try:
            sub = TenantSubscription.objects.get(tenant=tenant)
            sub.auto_renew = not sub.auto_renew
            sub.save()
            return Response({"status": "success", "auto_renew": sub.auto_renew})
        except TenantSubscription.DoesNotExist:
            return Response({"error": "No subscription found"}, status=404)


class ListInvoicesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=404)

        stripe_customer_id = getattr(tenant, "stripe_customer_id", None)
        if not stripe_customer_id:
            return Response([], status=200)  # Safe empty list

        try:
            invoices = stripe.Invoice.list(customer=stripe_customer_id, limit=50)
            formatted = [
                {
                    "id": inv.id,
                    "number": getattr(inv, "number", None),
                    "amount_due": inv.amount_due,
                    "status": inv.status,
                    "pdf": getattr(inv, "invoice_pdf", None),
                    "created": inv.created,
                }
                for inv in invoices.auto_paging_iter()
            ]
            return Response(formatted)
        except stripe.error.StripeError as e:
            # Log the error and return empty list
            print(f"Stripe Invoice list error for tenant {tenant.id}: {str(e)}")
            return Response([], status=200)


class CreateSetupIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        print(">>> ENTERED CreateSetupIntentView")

        user = request.user
        tenant_slug = request.headers.get("X-Tenant-Slug")

        if not tenant_slug:
            return Response({"error": "Tenant header missing"}, status=400)

        tenant_user = TenantUser.objects.filter(
            user=user,
            tenant__subdomain=tenant_slug
        ).first()

        print("TENANT USER:", tenant_user)

        if not tenant_user:
            return Response(
                {"error": "User does not belong to this tenant"},
                status=403
            )

        try:
            if not tenant_user.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    metadata={"tenant": tenant_slug},
                )
                tenant_user.stripe_customer_id = customer.id
                tenant_user.save()

            print("Stripe customer ID:", tenant_user.stripe_customer_id)

            intent = stripe.SetupIntent.create(
                customer=tenant_user.stripe_customer_id,
                payment_method_types=["card"],
                usage="off_session",
            )

            return Response({
                "clientSecret": intent.client_secret,
            })

        except stripe.error.StripeError as e:
            print("STRIPE ERROR:", e)
            return Response(
                {"error": e.user_message or str(e)},
                status=400
            )


        




class ListPaymentMethods(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=404)

        stripe_customer_id = getattr(tenant, "stripe_customer_id", None)
        if not stripe_customer_id:
            return Response([], status=200)  # Safe empty list

        try:
            # ✅ Get the Stripe customer to find default PM
            customer = stripe.Customer.retrieve(stripe_customer_id)
            default_pm_id = customer.invoice_settings.default_payment_method

            # ✅ List all payment methods
            payment_methods = stripe.PaymentMethod.list(
                customer=stripe_customer_id,
                type="card",
            )

            methods = [
                {
                    "id": pm.id,
                    "brand": pm.card.brand,
                    "last4": pm.card.last4,
                    "exp_month": pm.card.exp_month,
                    "exp_year": pm.card.exp_year,
                    "is_default": pm.id == default_pm_id,  # 🔑 Boolean
                }
                for pm in payment_methods.data
            ]

            return Response(methods)

        except stripe.error.StripeError as e:
            print(f"Stripe PaymentMethod list error for tenant {tenant.id}: {str(e)}")
            return Response([], status=200)



class SetDefaultPaymentMethod(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        payment_method_id = request.data.get("payment_method_id")
        tenant = get_current_tenant()

        if not payment_method_id:
            return Response({"error": "payment_method_id is required"}, status=400)

        tenant_user = TenantUser.objects.filter(user=user, tenant=tenant).first()
        if not tenant_user or not tenant_user.stripe_customer_id:
            return Response({"error": "Stripe customer not found"}, status=400)

        customer_id = tenant_user.stripe_customer_id

        try:
            # 🔑 Ensure PM is attached
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer_id,
            )

            # ✅ Set as default for invoices
            stripe.Customer.modify(
                customer_id,
                invoice_settings={
                    "default_payment_method": payment_method_id
                }
            )

            # ✅ Optional: update active subscription
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                status="active",
                limit=1,
            )

            if subscriptions.data:
                stripe.Subscription.modify(
                    subscriptions.data[0].id,
                    default_payment_method=payment_method_id,
                )

            tenant_user.default_payment_method_id = payment_method_id
            tenant_user.save()

            return Response({"success": True})

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=400)




class CreateSubscriptionWithSavedCardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = get_current_tenant()
        user = request.user
        plan_id = request.data.get("plan_id")

        logger.info(f"Change plan request: tenant={tenant}, user={user}, plan_id={plan_id}")

        if not tenant or not plan_id:
            return Response({"error": "Tenant or plan_id missing"}, status=400)

        # Fetch the new plan
        try:
            plan = SubscriptionPlan.objects.get(id=int(plan_id))
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Plan not found"}, status=404)

        # Fetch tenant user and Stripe customer
        tenant_user = TenantUser.objects.filter(user=user, tenant=tenant).first()
        if not tenant_user or not tenant_user.stripe_customer_id:
            return Response({"error": "No Stripe customer found"}, status=400)

        # Default payment method
        default_pm = getattr(tenant_user, "default_payment_method_id", None)
        if not default_pm:
            try:
                stripe_customer = stripe.Customer.retrieve(tenant_user.stripe_customer_id)
                default_pm = stripe_customer['invoice_settings']['default_payment_method']
                if not default_pm:
                    return Response({"error": "No default payment method. Add a card."}, status=400)
                tenant_user.default_payment_method_id = default_pm
                tenant_user.save()
            except Exception as e:
                logger.exception("Error retrieving Stripe customer default payment method")
                return Response({"error": str(e)}, status=500)

        # Fetch active subscription
        subscription = TenantSubscription.objects.filter(tenant=tenant, active=True).first()
        if not subscription or not subscription.stripe_subscription_id:
            return Response({"error": "No active subscription to update"}, status=400)

        try:
            # Fetch subscription items
            subscription_items = stripe.SubscriptionItem.list(subscription=subscription.stripe_subscription_id)
            if not subscription_items.data:
                return Response({"error": "Subscription has no items"}, status=400)

            # Modify first item (primary plan)
            item_id = subscription_items.data[0].id
            stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=False,
                proration_behavior="create_prorations",
                items=[{"id": item_id, "price": plan.stripe_price_id}],
                default_payment_method=default_pm
            )

            # Immediately create and finalize invoice for proration
            stripe.Invoice.create(
                customer=tenant_user.stripe_customer_id,
                auto_advance=True
            )

            # Retrieve updated subscription to get current_period_end
            stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
            end_timestamp = getattr(stripe_sub, 'current_period_end', None)

            # Fallback if current_period_end missing
            if not end_timestamp:
                logger.warning("current_period_end missing, falling back to 30 days from now")
                end_timestamp = int((timezone.now() + timedelta(days=30)).timestamp())

            # Update subscription in DB
            subscription.plan = plan
            subscription.end_date = datetime.fromtimestamp(end_timestamp, tz=dt_timezone.utc).date()
            subscription.max_users = plan.max_users
            subscription.max_dashboards = plan.max_dashboards
            subscription.max_datasets = plan.max_datasets
            subscription.max_api_rows = plan.max_api_rows
            subscription.save()

            return Response({"status": "success", "subscription": subscription.id})

        except stripe.error.StripeError as e:
            logger.exception("Stripe error during plan change")
            return Response({"error": str(e)}, status=400)
        except Exception as e:
            logger.exception("Unexpected error during plan change")
            return Response({"error": str(e)}, status=500)
        

class DeletePaymentMethod(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        payment_method_id = request.data.get("payment_method_id")
        tenant = get_current_tenant()

        if not payment_method_id or not tenant:
            return Response({"error": "Missing payment_method_id or tenant"}, status=400)

        tenant_user = TenantUser.objects.filter(user=user, tenant=tenant).first()
        if not tenant_user or not tenant_user.stripe_customer_id:
            return Response({"error": "Stripe customer not found"}, status=400)

        try:
            customer = stripe.Customer.retrieve(tenant_user.stripe_customer_id)
            if customer.invoice_settings.default_payment_method == payment_method_id:
                return Response({"error": "Cannot delete default payment method"}, status=400)

            stripe.PaymentMethod.detach(payment_method_id)
            return Response({"success": True})

        except Exception as e:
            return Response({"error": str(e)}, status=400)