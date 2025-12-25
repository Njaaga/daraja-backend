from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from .models import Tenant, TenantUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail


# -------------------------
# TENANT SIGNUP
# -------------------------
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

from django.contrib.auth import get_user_model

User = get_user_model()


def build_frontend_url(request, path: str) -> str:
    """
    Builds a subdomain-aware frontend URL.
    - localhost → http://tenant.localhost:3000
    - production → https://tenant.domain.com
    """

    protocol = "https" if not settings.DEBUG else "http"

    raw_host = request.get_host().split(":")[0]

    # DEV (localhost)
    if "localhost" in raw_host:
        frontend_port = getattr(settings, "FRONTEND_PORT", 3000)
        return f"{protocol}://{raw_host}:{frontend_port}{path}"

    # PROD
    frontend_domain = getattr(settings, "FRONTEND_DOMAIN", raw_host)
    return f"{protocol}://{frontend_domain}{path}"


@api_view(["POST"])
@permission_classes([AllowAny])
def tenant_signup(request):
    name = request.data.get("name")
    subdomain = request.data.get("subdomain")
    email = request.data.get("email")
    password = request.data.get("password")

    # -------------------- Validation --------------------
    if not all([name, subdomain, email, password]):
        return Response({"error": "All fields are required"}, status=400)

    if Tenant.objects.filter(subdomain=subdomain).exists():
        return Response({"error": "Subdomain already exists"}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already registered"}, status=400)

    # -------------------- Create Tenant --------------------
    tenant = Tenant.objects.create(
        name=name,
        subdomain=subdomain,
    )

    # -------------------- Create Stripe Customer --------------------
    try:
        stripe_customer = stripe.Customer.create(
            name=name,
            email=email,
            metadata={
                "tenant_id": tenant.id,
                "subdomain": subdomain,
            },
        )
        tenant.stripe_customer_id = stripe_customer.id
        tenant.save()
    except Exception as e:
        tenant.delete()
        return Response(
            {"error": f"Stripe customer creation failed: {str(e)}"},
            status=500,
        )

    # -------------------- Create Superadmin User --------------------
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        is_active=False,
        is_staff=True,
        is_superuser=True,
    )

    TenantUser.objects.create(
        tenant=tenant,
        user=user,
        stripe_customer_id=stripe_customer.id,
        is_superadmin = True,

    )

    # -------------------- Email Verification --------------------
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    verify_url = build_frontend_url(
        request,
        f"/verify-email?uid={uid}&token={token}",
    )

    send_mail(
        subject="Verify your email",
        message=(
            f"Welcome to {tenant.name}!\n\n"
            f"Please verify your email by clicking the link below:\n\n"
            f"{verify_url}\n\n"
            f"If you did not sign up, please ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )

    return Response(
        {
            "message": "Signup successful. Please verify your email.",
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "subdomain": tenant.subdomain,
            },
            "stripe_customer_id": tenant.stripe_customer_id,
        },
        status=201,
    )



@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    uidb64 = request.data.get("uid")
    token = request.data.get("token")

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({"error": "Invalid verification link"}, status=400)

    if not default_token_generator.check_token(user, token):
        return Response({"error": "Invalid or expired token"}, status=400)

    user.is_active = True
    user.save()

    return Response({"message": "Email verified successfully. You can now log in."})





@api_view(["POST"])
@permission_classes([AllowAny])
def tenant_login(request):
    """
    Tenant-aware login.
    Tenant is resolved from the user's tenant membership,
    NOT from frontend input.
    """

    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response(
            {"error": "Email and password are required"},
            status=400
        )

    # Authenticate user
    user = authenticate(request, username=email, password=password)
    if not user:
        return Response({"error": "Invalid credentials"}, status=401)

    # Resolve tenant via membership
    tenant_user = (
        TenantUser.objects
        .select_related("tenant")
        .filter(user=user)
        .first()
    )

    if not tenant_user:
        return Response(
            {"error": "User is not assigned to any tenant"},
            status=403
        )

    tenant = tenant_user.tenant

    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)

    # Subscription info (safe)
    subscription = getattr(user, "subscription", None)
    subscription_data = {
        "is_active": subscription.is_active if subscription else False,
        "plan": subscription.plan.name if subscription and subscription.plan else None,
    }

    # Role & superadmin
    is_superadmin = user.is_superuser
    role = "superadmin" if is_superadmin else getattr(user, "role", "user")

    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),

        # 🔑 THIS IS THE IMPORTANT PART
        "tenant": tenant.subdomain,  # ✅ slug / subdomain ONLY

        "email": user.email,
        "subscription": subscription_data,
        "is_superadmin": is_superadmin,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": role,
        },
    })



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    user = request.user
    tenant_user = getattr(user, "tenantuser", None)
    tenant = tenant_user.tenant if tenant_user else None
    subscription = getattr(tenant, "tenantsubscription", None)

    subscription_data = {
        "is_active": subscription.active if subscription else False,
        "plan": subscription.plan.name if subscription and subscription.plan else None,
    }

    return Response({
        "email": user.email,
        "tenant": tenant.subdomain if tenant else None,
        "subscription": subscription_data,
        "is_superadmin": user.is_superuser,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": "superadmin" if user.is_superuser else getattr(user, "role", "user"),
        },
    })