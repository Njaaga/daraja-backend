# subscriptions/views.py
import stripe
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

stripe.api_key = settings.STRIPE_SECRET_KEY
FRONTEND_URL = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')


class ListPlansView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.all().values("id", "name", "price")
        return Response(plans)


class CreateStripeCheckoutSession(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Get tenant without passing request
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=400)

        plan_id = request.data.get("plan_id")
        if not plan_id:
            return Response({"error": "Missing plan_id"}, status=400)

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Plan not found"}, status=404)

        if not plan.stripe_price_id:
            return Response({"error": "Plan missing Stripe price ID"}, status=400)

        # Create Stripe customer if not exists
        if not tenant.stripe_customer_id:
            admin = User.objects.filter(
                tenantuser__tenant=tenant,
                is_superuser=True
            ).first()
            if not admin:
                return Response({"error": "Tenant admin missing"}, status=400)

            customer = stripe.Customer.create(
                email=admin.email,
                metadata={"tenant": tenant.subdomain},
            )
            tenant.stripe_customer_id = customer.id
            tenant.save()

        # Build frontend URLs with tenant subdomain (local dev)
        if settings.DEBUG:
            frontend_host = f"{tenant.subdomain}.localhost:3000"
            success_url = f"http://{frontend_host}/billing?success=1&tenant={tenant.subdomain}"
            cancel_url = f"http://{frontend_host}/billing?canceled=1&tenant={tenant.subdomain}"
        else:
            # Production
            success_url = f"{settings.FRONTEND_URL}/billing?success=1&tenant={tenant.subdomain}"
            cancel_url = f"{settings.FRONTEND_URL}/billing?canceled=1&tenant={tenant.subdomain}"

        # Create Stripe checkout session
        session = stripe.checkout.Session.create(
            customer=tenant.stripe_customer_id,
            mode="subscription",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            metadata={"tenant_subdomain": tenant.subdomain, "plan_id": str(plan.id)},
            subscription_data={"metadata": {"tenant_subdomain": tenant.subdomain, "plan_id": str(plan.id)}},
            success_url=success_url,
            cancel_url=cancel_url,
        )

        return Response({"url": session.url})




@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    print("🔥 Stripe webhook received")

    # Verify Stripe signature
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        print("✅ Event verified:", event["type"])
    except Exception as e:
        print("❌ Webhook signature error:", e)
        return HttpResponse(status=400)

    # Handle checkout.session.completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print("Session object:", session)

        subscription_id = session.get("subscription")
        metadata = session.get("metadata", {})
        tenant_subdomain = metadata.get("tenant_subdomain")
        plan_id = metadata.get("plan_id")

        # Debug missing metadata
        if not all([subscription_id, tenant_subdomain, plan_id]):
            print(f"❌ Missing info in webhook: subscription_id={subscription_id}, tenant_subdomain={tenant_subdomain}, plan_id={plan_id}")
            return HttpResponse(status=400)

        try:
            # Get tenant and plan
            tenant = Tenant.objects.get(subdomain=tenant_subdomain)
            plan = SubscriptionPlan.objects.get(id=plan_id)

            # Retrieve full Stripe subscription to get period_end
            stripe_sub = stripe.Subscription.retrieve(subscription_id)
            current_period_end = timezone.datetime.fromtimestamp(
                stripe_sub["current_period_end"], tz=timezone.utc
            )

            # Save or update subscription in DB
            sub, created = TenantSubscription.objects.update_or_create(
                tenant=tenant,
                defaults={
                    "plan": plan,
                    "active": True,
                    "start_date": timezone.now(),
                    "end_date": current_period_end.date(),
                    "stripe_subscription_id": subscription_id,
                    "max_users": plan.max_users,
                    "max_dashboards": plan.max_dashboards,
                    "max_datasets": plan.max_datasets,
                    "max_api_rows": plan.max_api_rows,
                    "auto_renew": True,
                },
            )

            print(f"✅ Subscription {'created' if created else 'updated'} in DB: {sub.id} for tenant {tenant.subdomain}")

        except Tenant.DoesNotExist:
            print(f"❌ Tenant not found: {tenant_subdomain}")
            return HttpResponse(status=400)
        except SubscriptionPlan.DoesNotExist:
            print(f"❌ Plan not found: {plan_id}")
            return HttpResponse(status=400)
        except Exception as e:
            print("❌ DB error:", e)
            return HttpResponse(status=500)

    # Handle other events here if needed
    else:
        print(f"ℹ️ Unhandled event type: {event['type']}")

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
        tenant = get_current_tenant()

        # Always return 200
        if not tenant:
            return Response({
                "active": False,
                "current_plan": None,
                "available_plans": []
            })

        sub = (
            TenantSubscription.objects
            .select_related("plan")
            .filter(tenant=tenant, active=True)
            .first()
        )

        is_active = (
            sub
            and (not sub.end_date or sub.end_date >= timezone.now().date())
        )

        current_plan = None
        if is_active:
            current_plan = {
                "id": sub.plan.id,
                "name": sub.plan.name,
                "price": sub.plan.price,
                "start_date": sub.start_date,
                "end_date": sub.end_date,
                "auto_renew": sub.auto_renew,
                "limits": {
                    "users": sub.max_users,
                    "dashboards": sub.max_dashboards,
                    "datasets": sub.max_datasets,
                    "api_rows": sub.max_api_rows,
                },
            }

        plans_qs = SubscriptionPlan.objects.all()
        if current_plan:
            plans_qs = plans_qs.exclude(id=current_plan["id"])

        available_plans = list(
            plans_qs.values("id", "name", "price")
        )

        return Response({
            "active": bool(current_plan),
            "current_plan": current_plan,
            "available_plans": available_plans,
        })



class CancelSubscriptionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=404)
        try:
            sub = TenantSubscription.objects.get(tenant=tenant)
            if sub.stripe_subscription_id:
                try:
                    stripe.Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
                except Exception:
                    pass
            sub.active = False
            sub.end_date = timezone.now().date()
            sub.save()
            return Response({"status": "success", "message": "Subscription canceled."})
        except TenantSubscription.DoesNotExist:
            return Response({"error": "No subscription found to cancel."}, status=404)


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
    permission_classes = [AllowAny]

    def get(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=404)
        if not getattr(tenant, "stripe_customer_id", None):
            return Response([], status=200)
        try:
            invoices = stripe.Invoice.list(customer=tenant.stripe_customer_id, limit=50)
            formatted = []
            for inv in invoices.auto_paging_iter():
                formatted.append({
                    "id": inv.id,
                    "number": getattr(inv, "number", None),
                    "amount_due": inv.amount_due,
                    "status": inv.status,
                    "pdf": inv.invoice_pdf if hasattr(inv, "invoice_pdf") else None,
                    "created": inv.created,
                })
            return Response(formatted)
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class CreateSetupIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        tenant_subdomain = request.headers.get("X-Tenant-Subdomain")

        if not tenant_subdomain:
            return Response({"error": "Tenant header missing"}, status=400)

        tenant_user = TenantUser.objects.filter(
            user=user,
            tenant__subdomain=tenant_subdomain
        ).first()

        if not tenant_user:
            return Response({"error": "User does not belong to this tenant"}, status=403)

        try:
            if not tenant_user.stripe_customer_id:
                customer = stripe.Customer.create(
                    email=user.email,
                    metadata={"tenant": tenant_subdomain},
                )
                tenant_user.stripe_customer_id = customer.id
                tenant_user.save()

            intent = stripe.SetupIntent.create(
                customer=tenant_user.stripe_customer_id,
                payment_method_types=["card"],
                usage="off_session",
            )

            return Response({
                "clientSecret": intent.client_secret,
            })

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=400)




class ListPaymentMethods(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=400)
        tenant_user = TenantUser.objects.filter(user=user, tenant=tenant).first()
        if not tenant_user or not tenant_user.stripe_customer_id:
            return Response({"methods": []})
        try:
            pms = stripe.PaymentMethod.list(customer=tenant_user.stripe_customer_id, type="card")
            formatted = [{
                "id": pm.id,
                "brand": pm.card.brand,
                "last4": pm.card.last4,
                "exp_month": pm.card.exp_month,
                "exp_year": pm.card.exp_year,
                "is_default": pm.id == getattr(tenant_user, "default_payment_method_id", None),
            } for pm in pms.data]
            return Response({"methods": formatted})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class SetDefaultPaymentMethod(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        payment_method_id = request.data.get("payment_method_id")
        if not payment_method_id:
            return Response({"error": "payment_method_id is required"}, status=400)
        tenant = get_current_tenant()
        if not tenant:
            return Response({"error": "Tenant not found"}, status=400)
        tenant_user = TenantUser.objects.filter(user=user, tenant=tenant).first()
        if not tenant_user or not tenant_user.stripe_customer_id:
            return Response({"error": "Stripe customer not found"}, status=400)
        try:
            stripe.Customer.modify(
                tenant_user.stripe_customer_id, invoice_settings={"default_payment_method": payment_method_id}
            )
            tenant_user.default_payment_method_id = payment_method_id
            tenant_user.save()
            return Response({"success": True})
        except Exception as e:
            return Response({"error": str(e)}, status=400)



class CreateSubscriptionWithSavedCardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = get_current_tenant()
        user = request.user
        plan_id = request.data.get("plan_id")

        if not tenant or not plan_id:
            return Response({"error": "Tenant or plan_id missing"}, status=400)

        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({"error": "Plan not found"}, status=404)

        tenant_user = TenantUser.objects.filter(user=user, tenant=tenant).first()
        if not tenant_user or not tenant_user.stripe_customer_id:
            return Response({"error": "No Stripe customer found"}, status=400)

        # Get default payment method
        default_pm = getattr(tenant_user, "default_payment_method_id", None)
        if not default_pm:
            return Response({"error": "No default payment method"}, status=400)

        try:
            stripe_sub = stripe.Subscription.create(
                customer=tenant_user.stripe_customer_id,
                items=[{"price": plan.stripe_price_id}],
                default_payment_method=default_pm,
                metadata={"tenant_subdomain": tenant.subdomain, "plan_id": str(plan.id)}
            )

            # Save subscription in DB
            sub, _ = TenantSubscription.objects.get_or_create(tenant=tenant)
            sub.plan = plan
            sub.stripe_subscription_id = stripe_sub.id
            sub.start_date = timezone.now()
            sub.end_date = timezone.datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc).date()
            sub.active = True
            sub.max_users = plan.max_users
            sub.max_dashboards = plan.max_dashboards
            sub.max_datasets = plan.max_datasets
            sub.max_api_rows = plan.max_api_rows
            sub.save()

            return Response({"status": "success", "subscription": sub.id})
        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=400)
