import time
import logging
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from django.core.mail import EmailMessage
from .models import (
    Dashboard, 
    Group, 
    ApiDataSource,     
    Dataset,
    Chart,
    Dashboard,
    DashboardChart,
    Dataset
)
from .serializers import (
    UserSerializer, 
    DashboardSerializer, 
    GroupSerializer, 
    ApiDataSourceSerializer,
    DatasetSerializer,
    ChartSerializer,
    DashboardSerializer,
    DashboardChartSerializer,
)
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
import requests
from urllib.parse import urljoin
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .serializers import UserSerializer, GroupNestedSerializer, TenantSignupSerializer
from tenants.middleware import get_current_tenant
from tenants.models import TenantUser
from subscriptions.utils.subscription_limits import enforce_subscription_limit
from django.db.models import Q
from .permissions import IsSuperAdmin
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.tokens import AccessToken
from datetime import timedelta
from rest_framework.parsers import JSONParser
from django.db import IntegrityError
from rest_framework.exceptions import APIException
import requests
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from dashboards.services.oauth import refresh_quickbooks_token
from rest_framework.decorators import action
from collections import defaultdict
from dashboards.services.dataset_runner import run_dataset
from dashboards.services.transform import transform_rows
import traceback
from dashboards.utils import apply_logic_rules, apply_calculated_fields, apply_filters
from .utils import transform_rows_safe

# ---------------------------
# USERS
# ---------------------------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    # -----------------------------
    # Queryset (active by default)
    # -----------------------------


    @action(detail=False, methods=["post"], permission_classes=[AllowAny], url_path="set-password")
    def set_password(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("password")

        if not uid or not token or not password:
            return Response({"error": "Missing data"}, status=400)

        try:
            uid = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid user"}, status=400)

        if default_token_generator.check_token(user, token):
            user.set_password(password)
            user.save()
            return Response({"success": True, "message": "Password set successfully"})
        else:
            return Response({"error": "Invalid or expired token"}, status=400)
            
    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return User.objects.none()

        qs = User.objects.filter(tenantuser__tenant=tenant)

        include_deleted = self.request.query_params.get("include_deleted")
        if include_deleted != "true":
            qs = qs.filter(is_active=True)

        return qs.order_by("first_name", "last_name")

    @action(detail=False, methods=["post"], url_path="invite")
    def invite(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response(
                {"detail": "Tenant not detected"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    
        # 🚨 Subscription limit
        enforce_subscription_limit(tenant, resource="users")
    
        # Validate input
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
    
        data = serializer.validated_data
        email = data.get("email").lower().strip()
    
        # Check if user already exists in this tenant
        if TenantUser.objects.filter(user__email=email, tenant=tenant).exists():
            return Response(
                {"error": "User with this email already exists in tenant"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    
        # Manually create user (avoid passing tenant to User)
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            is_active=True,
        )
    
        # Attach tenant
        TenantUser.objects.get_or_create(user=user, tenant=tenant)
    
        # -----------------------------
        # INVITE EMAIL WITH TOKEN ✅
        # -----------------------------
        try:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
    
            setup_link = f"{settings.FRONTEND_URL}/set-password?uid={uid}&token={token}"
    
            send_mail(
                subject="You’ve been invited",
                message=f"You’ve been invited.\n\nSet your password here:\n{setup_link}\n\nThis link will expire.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,  # never break user creation
            )
        except Exception as e:
            print("Invite email failed:", str(e))
    
        return Response(
            {"message": "User invited successfully"},
            status=status.HTTP_201_CREATED,
        )




    
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk_invite",
    )
    def bulk_invite(self, request):
        tenant = get_current_tenant()
        if not tenant:
            return Response(
                {"detail": "Tenant not detected"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    
        users = request.data.get("users", [])
    
        if not isinstance(users, list) or not users:
            return Response(
                {"detail": "users must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    
        invited = []
        failed = []
    
        for user_data in users:
            serializer = self.get_serializer(data=user_data)
    
            if not serializer.is_valid():
                failed.append({
                    "email": user_data.get("email"),
                    "error": serializer.errors,
                })
                continue
    
            data = serializer.validated_data
            email = data["email"].lower().strip()
    
            # Already exists in tenant
            if TenantUser.objects.filter(user__email=email, tenant=tenant).exists():
                failed.append({
                    "email": email,
                    "error": "User already exists in tenant",
                })
                continue
    
            try:
                # Enforce per-user subscription
                enforce_subscription_limit(tenant, resource="users")
    
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    first_name=data.get("first_name", ""),
                    last_name=data.get("last_name", ""),
                    is_active=True,
                )
    
                TenantUser.objects.create(user=user, tenant=tenant)
    
                # Invite email
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                setup_link = (
                    f"{settings.FRONTEND_URL}/set-password"
                    f"?uid={uid}&token={token}"
                )
    
                send_mail(
                    subject="You’ve been invited",
                    message=(
                        "You’ve been invited.\n\n"
                        f"Set your password here:\n{setup_link}\n\n"
                        "This link will expire."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=True,
                )
    
                invited.append(email)
    
            except IntegrityError:
                failed.append({
                    "email": email,
                    "error": "User already exists",
                })
    
            except Exception as e:
                failed.append({
                    "email": email,
                    "error": str(e),
                })
    
        return Response(
            {
                "invited_count": len(invited),
                "invited": invited,
                "failed": failed,
            },
            status=status.HTTP_201_CREATED,
        )


        
    # -----------------------------
    # Create user (limit enforced)
    # -----------------------------
    def perform_create(self, serializer):
        tenant = get_current_tenant()
        enforce_subscription_limit(tenant, resource="users")

        user = serializer.save(is_active=True)
        TenantUser.objects.get_or_create(user=user, tenant=tenant)

    # -----------------------------
    # Soft delete (override DELETE)
    # -----------------------------
    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    # -----------------------------
    # Restore user
    # -----------------------------
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        tenant = get_current_tenant()
        enforce_subscription_limit(tenant, resource="users")

        try:
            user = User.objects.get(
                pk=pk,
                tenantuser__tenant=tenant,
                is_active=False
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found or already active"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.is_active = True
        user.save(update_fields=["is_active"])

        return Response({"message": "User restored successfully"})

    @action(detail=True, methods=["delete"], url_path="hard_delete")
    def hard_delete(self, request, pk=None):
        tenant = get_current_tenant()

        try:
            user = User.objects.get(
                pk=pk,
                tenantuser__tenant=tenant,
                is_active=False,  # must already be soft-deleted
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found or not in recycle bin"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.delete()

        return Response(
            {
                "success": True,
                "message": "User permanently deleted"
            },
            status=status.HTTP_200_OK
        )


class SetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("password")

        if not uid or not token or not password:
            return Response({"error": "Missing data"}, status=400)

        try:
            uid = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid user"}, status=400)

        if default_token_generator.check_token(user, token):
            user.set_password(password)
            user.save()
            return Response({"success": True, "message": "Password set successfully"})
        else:
            return Response({"error": "Invalid or expired token"}, status=400)
            
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    """
    Handles forgot password requests:
    - User submits email
    - Generates a short-lived JWT for password reset
    - Sends reset link via email
    """

    def post(self, request):
        email = request.data.get("email")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Do not reveal user existence for security
            return Response({"message": "If the email exists, a reset link was sent"})

        # Generate JWT for password reset
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(minutes=30))  # token expires in 30 minutes
        token["type"] = "reset_password"

        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={str(token)}"

        send_mail(
            subject="Reset your password",
            message=f"Click here to reset your password:\n{reset_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )

        return Response({"message": "Password reset email sent"})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    """
    Handles password reset:
    - Receives JWT + new password
    - Validates JWT and updates password
    """

    def post(self, request):
        token_str = request.data.get("token")
        new_password = request.data.get("password")

        if not token_str or not new_password:
            return Response({"error": "Token and password are required"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            token = AccessToken(token_str)
        except Exception:
            return Response({"error": "Invalid token"},
                            status=status.HTTP_400_BAD_REQUEST)

        if token.get("type") != "reset_password":
            return Response({"error": "Invalid token type"},
                            status=status.HTTP_400_BAD_REQUEST)

        user_id = token["user_id"]
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"},
                            status=status.HTTP_404_NOT_FOUND)

        user.set_password(new_password)
        user.save()

        return Response({"message": "Password reset successful"})

    
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    
# -------------------------
# PASSWORD SETUP VIEW
# -------------------------

@method_decorator(csrf_exempt, name="dispatch")
class PasswordSetupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("password")

        if not uid or not token or not password:
            return Response({"error": "Missing data"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid user"}, status=status.HTTP_400_BAD_REQUEST)

        if default_token_generator.check_token(user, token):
            user.set_password(password)
            user.save()
            return Response({"success": True, "message": "Password set successfully"})
        else:
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------
# GROUPS
# ---------------------------
class GroupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Group.objects.none()
    
        user = self.request.user
    
        qs = Group.objects.filter(tenant=tenant)
    
        # Allow restore & hard delete to access deleted records
        if self.action in ["restore", "hard_delete"]:
            return qs
    
        # Recycle bin view (admins only, implicitly)
        if self.request.query_params.get("recycle") == "true":
            return qs.filter(is_deleted=True)
    
        # Default: active only
        qs = qs.filter(is_deleted=False)
    
        # 🔐 ROLE-BASED FILTERING
        if user.is_superuser or user.is_staff:
            return qs
    
        # 👤 Normal users → only groups they are assigned to
        return qs.filter(users=user)




    def get_serializer_class(self):
        if self.request.method in ["GET"]:
            return GroupNestedSerializer
        return GroupSerializer

    def perform_create(self, serializer):
        tenant = get_current_tenant()

        # 🚨 Enforce subscription dataset limit
        enforce_subscription_limit(tenant, "groups")

        serializer.save(tenant=tenant)
        

    @action(detail=True, methods=["post"])
    def assign_users(self, request, pk=None):
        tenant = get_current_tenant()
        group = self.get_object()
        user_ids = request.data.get("user_ids", [])
        users = User.objects.filter(id__in=user_ids, tenantuser__tenant=tenant)
        group.users.set(users)
        group.save()
        return Response({"success": True, "message": "Users assigned"})

    @action(detail=True, methods=["post"])
    def assign_dashboards(self, request, pk=None):
        tenant = get_current_tenant()
        group = self.get_object()
        dashboard_ids = request.data.get("dashboard_ids", [])
        dashboards = Dashboard.objects.filter(id__in=dashboard_ids, tenant=tenant)
        group.dashboards.set(dashboards)
        group.save()
        return Response({"success": True, "message": "Dashboards assigned"})

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()

        group.is_deleted = True
        group.deleted_at = timezone.now()
        group.save(update_fields=["is_deleted", "deleted_at"])

        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        group = self.get_object()

        group.is_deleted = False
        group.deleted_at = None
        group.save(update_fields=["is_deleted", "deleted_at"])

        return Response({"success": True})
    
    @action(detail=True, methods=["delete"])
    def hard_delete(self, request, pk=None):
        group = self.get_object()
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)





# ---------- Data Sources ----------
class ApiDataSourceViewSet(viewsets.ModelViewSet):
    serializer_class = ApiDataSourceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        show_deleted = self.request.query_params.get("show_deleted") == "true"
        qs = ApiDataSource.objects.filter(tenant=tenant)
        return qs if show_deleted else qs.filter(is_deleted=False)

    def get_object(self):
        tenant = get_current_tenant()
        return get_object_or_404(
            ApiDataSource, pk=self.kwargs["pk"], tenant=tenant
        )

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        enforce_subscription_limit(tenant, "datasources")
        serializer.save(
            tenant=tenant,
            created_by=self.request.user,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])
        return Response({"success": True})

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        instance = self.get_object()
        instance.is_deleted = False
        instance.save(update_fields=["is_deleted"])
        return Response({"success": True})

    @action(detail=True, methods=["delete"])
    def hard_delete(self, request, pk=None):
        instance = self.get_object()
        instance.delete()
        return Response({"success": True})

    # ---------------- QuickBooks Entity Fields Endpoint ----------------
    @action(
        detail=True,
        methods=["get"],
        url_path=r"entities/(?P<entity>[^/.]+)/fields"
    )
    def entity_fields(self, request, pk=None, entity=None):
        """
        Returns REAL QuickBooks entity fields by querying QB
        Endpoint:
        /api/sources/{id}/entities/{entity}/fields/
        """
    
        api_source = self.get_object()
    
        # ----------------------------
        # Validate provider
        # ----------------------------
        if api_source.provider.lower() != "quickbooks":
            return Response(
                {"error": "Not a QuickBooks API source"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
        if not api_source.bearer_token or not api_source.base_url:
            return Response(
                {"error": "QuickBooks source is not authenticated"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
        # ----------------------------
        # Normalize entity name
        # ----------------------------
        ENTITY_MAP = {
            "invoice": "Invoice",
            "customer": "Customer",
            "payment": "Payment",
            "account": "Account",
            "item": "Item",
        }
    
        entity_key = entity.lower()
        qb_entity = ENTITY_MAP.get(entity_key)
    
        if not qb_entity:
            return Response(
                {"error": f"Unsupported entity: {entity}"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
        # ----------------------------
        # Build QuickBooks Query URL
        # api_source.base_url MUST already include /v3/company/{company_id}
        # ----------------------------
        qb_query_url = f"{api_source.base_url}/query"
    
        query = f"SELECT * FROM {qb_entity} MAXRESULTS 1"
    
        headers = {
            "Authorization": f"Bearer {api_source.bearer_token}",
            "Accept": "application/json",
            "Content-Type": "application/text",
        }
    
        # ----------------------------
        # Execute QuickBooks query
        # ----------------------------
        try:
            resp = requests.post(
                qb_query_url,
                data=query,
                headers=headers,
                timeout=20,
            )
        except requests.RequestException as e:
            return Response(
                {"error": "Failed to connect to QuickBooks", "details": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
    
        # ----------------------------
        # Handle QuickBooks errors
        # ----------------------------
        if resp.status_code != 200:
            return Response(
                {
                    "error": "QuickBooks query failed",
                    "status_code": resp.status_code,
                    "qb_response": resp.json() if "json" in resp.headers.get("content-type", "") else resp.text,
                    "query": query,
                    "url": qb_query_url,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    
        data = resp.json()
        query_response = data.get("QueryResponse", {})
    
        records = query_response.get(qb_entity, [])
    
        if not records:
            return Response(
                {
                    "fields": [],
                    "warning": f"No records found for {qb_entity}"
                }
            )
    
        # ----------------------------
        # Extract fields dynamically
        # ----------------------------
        record = records[0]
    
        def extract_fields(obj, prefix=""):
            fields = []
            for key, value in obj.items():
                if isinstance(value, dict):
                    fields.extend(extract_fields(value, f"{prefix}{key}."))
                else:
                    fields.append(f"{prefix}{key}")
            return fields
    
        fields = sorted(set(extract_fields(record)))
    
        return Response({
            "entity": qb_entity,
            "fields": fields
        })


        
# ---------- Datasets ----------
class DatasetViewSet(viewsets.ModelViewSet):
    """
    Tenant-aware ViewSet for managing datasets.
    """
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        show_deleted = self.request.query_params.get("show_deleted")

        qs = Dataset.objects.filter(tenant=tenant)

        if show_deleted == "true":
            return qs.filter(is_deleted=True)

        return qs.filter(is_deleted=False)


    def perform_create(self, serializer):
        tenant = get_current_tenant()

        # 🚨 Enforce subscription dataset limit
        enforce_subscription_limit(tenant, "datasets")

        serializer.save(
            created_by=self.request.user,
            tenant=tenant
        )

    def get_object(self):
        tenant = get_current_tenant()
        return get_object_or_404(
            Dataset.objects.all(),  # ❗️do NOT filter is_deleted here
            id=self.kwargs["pk"],
            tenant=tenant
        )


    # ---------- Saved Dataset Run ----------
    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        dataset = self.get_object()
        return self._run_dataset(dataset)

    # ---------- Ad-Hoc Dataset Run ----------
    @action(detail=False, methods=["post"], url_path="adhoc-run")
    def adhoc_run(self, request):
        api_source_id = request.data.get("api_source")
        endpoint = request.data.get("endpoint")
        query_params = request.data.get("query_params", {})

        if not api_source_id or not endpoint:
            return Response(
                {"error": "api_source and endpoint are required for ad-hoc run."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ensure the API source belongs to the current tenant
        tenant = get_current_tenant()
        source = get_object_or_404(ApiDataSource, pk=api_source_id, tenant=tenant)

        dataset = Dataset(
            name="__adhoc__",
            api_source=source,
            endpoint=endpoint,
            entity=request.data.get("entity"),
            fields=request.data.get("fields", []),
            filters=request.data.get("filters", {}),
            query_params=query_params
        )
        return self._run_dataset(dataset)

    # ---------- Internal Dataset Runner ----------
    def _run_dataset(self, dataset):
        """
        Executes a dataset against its data source.
        Supports QuickBooks (POST /query) and generic REST APIs.
        """
        source = dataset.api_source
        params = dataset.query_params.copy() if dataset.query_params else {}
        headers = {}
    
        # ---------------- QuickBooks ----------------
        if source.provider.lower() == "quickbooks":
            # Ensure credentials
            if not source.bearer_token or not source.base_url:
                return Response(
                    {"error": "QuickBooks access token or base URL missing."},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
            # Refresh token if expired
            if getattr(source, "oauth_token_expires_at", None) and source.oauth_token_expires_at <= timezone.now():
                try:
                    refresh_quickbooks_token(source)
                except requests.RequestException as e:
                    return Response(
                        {"error": f"Failed to refresh QuickBooks token: {str(e)}"},
                        status=status.HTTP_502_BAD_GATEWAY
                    )
    
            headers = {
                "Authorization": f"Bearer {source.bearer_token}",
                "Accept": "application/json",
                "Content-Type": "application/text",  # QB expects raw query in body
            }
    
            # Get entity & fields
            entity = getattr(dataset, "entity", None)
            fields = getattr(dataset, "fields", None)
    
            if not entity:
                return Response(
                    {"error": "QuickBooks entity must be selected."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not fields or not isinstance(fields, list) or len(fields) == 0:
                return Response(
                    {"error": "Select at least one field for QuickBooks entity."},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
            # Build query
            query = f"SELECT {', '.join(fields)} FROM {entity}"
            filters = getattr(dataset, "filters", {}) or {}
            where_clauses = []
    
            # Date range filter
            if filters.get("date_field") and filters.get("from") and filters.get("to"):
                where_clauses.append(
                    f"{filters['date_field']} BETWEEN '{filters['from']}' AND '{filters['to']}'"
                )
    
            # Equals filters
            for k, v in filters.get("equals", {}).items():
                where_clauses.append(f"{k} = '{v}'")
    
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
    
            url = f"{source.base_url}/query"
    
            # Debug logs
            print("[QB QUERY]", query)
            print("[QB URL]", url)
    
            try:
                resp = requests.post(url, data=query, headers=headers, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
                print("[QB RESPONSE]", payload)
            except requests.RequestException as e:
                return Response(
                    {"error": "QuickBooks request failed", "details": str(e), "query": query},
                    status=status.HTTP_502_BAD_GATEWAY
                )
    
            # Check QuickBooks logical errors
            if "Fault" in payload:
                return Response(
                    {"error": "QuickBooks API error", "details": payload["Fault"], "query": query},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
            query_response = payload.get("QueryResponse", {})
            if not query_response:
                return Response({
                    "entity": entity,
                    "fields": fields,
                    "count": 0,
                    "data": []
                })
    
            # Extract rows (QB returns key by entity name)
            entity_key = next(iter(query_response.keys()), None)
            rows = query_response.get(entity_key, []) if entity_key else []
    
            return Response({
                "entity": entity,
                "fields": fields,
                "count": len(rows),
                "data": rows,
            })
    
        # ---------------- Generic REST APIs ----------------
        else:
            url = urljoin(
                source.base_url.rstrip("/") + "/",
                (dataset.endpoint or "").lstrip("/")
            )
    
            if source.auth_type == "API_KEY_HEADER" and source.api_key:
                headers[source.api_key_header] = source.api_key
            elif source.auth_type == "BEARER" and source.api_key:
                headers["Authorization"] = f"Bearer {source.api_key}"
            elif source.auth_type == "API_KEY_QUERY" and source.api_key:
                params[source.api_key_header] = source.api_key
    
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    
            # Flatten standard API responses
            if isinstance(data, dict):
                for k in ("results", "data", "rows"):
                    if k in data and isinstance(data[k], list):
                        data = data[k]
                        break
    
            return Response({"data": data})


    
    
    # ---------- QUICKBOOKS EXECUTOR ----------
    def _run_quickbooks_dataset(self, dataset):
        source = dataset.api_source
        qb = QuickBooksClient(source)  # your QB client
    
        fields = getattr(dataset, "fields", None) or ["Id"]
        entity = getattr(dataset, "entity", None)
        filters = getattr(dataset, "filters", None) or {}
    
        field_clause = ", ".join(fields)
        query = f"SELECT {field_clause} FROM {entity}"
    
        where_clauses = []
    
        # Date filter
        if filters.get("date_field") and filters.get("from") and filters.get("to"):
            where_clauses.append(
                f"{filters['date_field']} BETWEEN '{filters['from']}' AND '{filters['to']}'"
            )
    
        # Generic equality filters
        for key, value in filters.get("equals", {}).items():
            where_clauses.append(f"{key} = '{value}'")
    
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
    
        try:
            data = qb.query(query)  # should return list of dicts
    
            if not isinstance(data, list):
                data = []
    
            return Response({
                "meta": {
                    "entity": entity,
                    "fields": fields,
                    "count": len(data)
                },
                "data": data
            })
    
        except Exception as e:
            return Response({"error": f"QuickBooks query failed: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        

    def destroy(self, request, *args, **kwargs):
        dataset = self.get_object()
        dataset.is_deleted = True
        dataset.save()

        return Response(
            {"success": True, "message": "Dataset moved to recycle bin"},
            status=status.HTTP_200_OK
        )


    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        dataset = self.get_object()

        if not dataset.is_deleted:
            return Response(
                {"success": False, "message": "Dataset is not deleted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        dataset.is_deleted = False
        dataset.save()

        return Response(
            {"success": True, "message": "Dataset restored successfully."},
            status=status.HTTP_200_OK
        )
    
    
    @action(detail=True, methods=["delete"])
    def hard_delete(self, request, pk=None):
        dataset = self.get_object()
        dataset.delete()

        return Response(
            {"success": True, "message": "Dataset permanently deleted"},
            status=status.HTTP_200_OK
        )


# Ad-hoc run endpoint: POST /api/datasets/run/
from rest_framework.views import APIView
logger = logging.getLogger(__name__)  # use Django logger

class DatasetRunAdhocView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Run a dataset on-the-fly (ad-hoc) with optional field selection and filters.

        Body:
        {
            api_source: <id>,
            endpoint: "/path",
            query_params: {...},
            selected_fields: ["month", "sales"],
            filters: {"sales": {"min": 0, "max": 1000}},
            logic_rules: [...]
        }
        """
        data = request.data
        source_id = data.get("api_source")
        endpoint = data.get("endpoint")
        params = data.get("query_params", {})

        if not source_id or not endpoint:
            return Response(
                {"error": "api_source and endpoint required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        source = get_object_or_404(ApiDataSource, pk=source_id)
        dataset = Dataset(name="__adhoc__", api_source=source, endpoint=endpoint, query_params=params)

        # Run the dataset
        results = run_dataset_wicket(dataset)

        # Apply optional filters
        filters = data.get("filters") or {}
        logic_rules = data.get("logic_rules") or []
        selected_fields = data.get("selected_fields") or []

        # Filter rows based on filters & logic_rules
        if filters or logic_rules:
            from app.charts.utils import apply_logic_and_filters  # you can reuse frontend logic in Python
            results = apply_logic_and_filters(results, filters, logic_rules)

        # Return only selected fields
        if selected_fields:
            results = [
                {k: v for k, v in row.items() if k in selected_fields}
                for row in results
            ]

        return Response({"data": results})


def run_dataset_wicket(dataset):
    source = dataset.api_source
    endpoint = dataset.endpoint or ""
    url = urljoin(source.base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    # Merge query params
    params = {}
    if dataset.query_params:
        params.update(dataset.query_params)

    headers = {}

    logger.info(f"[DatasetRun] URL={url}, Auth={source.auth_type}, Params={params}")

    # --- AUTH LOGIC ---
    try:
        if source.auth_type == "API_KEY_HEADER" and source.api_key:
            headers[source.api_key_header] = source.api_key
            logger.info(f"[Auth] API Key in header: {source.api_key_header}=<hidden>")

        elif source.auth_type == "BEARER" and source.api_key:
            headers["Authorization"] = f"Bearer {source.api_key}"
            logger.info("[Auth] Bearer token used")

        elif source.auth_type == "API_KEY_QUERY" and source.api_key:
            params.update({"api_key": source.api_key})
            logger.info("[Auth] API Key added to query params")

        elif source.auth_type == "JWT_HS256":
            # Wicket JWT requirements
            payload = {
                "exp": int(time.time()) + (source.jwt_ttl_seconds or 300),  # short expiry
                "sub": source.jwt_subject,  # API admin UUID
                "aud": source.jwt_audience,  # tenant API URL
            }
            if source.jwt_issuer:
                payload["iss"] = source.jwt_issuer

            token = jwt.encode(payload, source.jwt_secret, algorithm="HS256")
            headers["Authorization"] = f"Bearer {token}"
            logger.info(f"[Auth] JWT token generated (truncated)={token[:20]}...")

        else:
            logger.warning(f"[Auth] No auth applied for auth_type={source.auth_type}")

    except Exception as e:
        logger.exception("JWT generation failed")
        return Response({"error": f"JWT generation failed: {str(e)}"}, status=500)

    # --- MAKE REQUEST ---
    try:
        logger.info(f"[Request] GET {url} Headers={headers} Params={params}")
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        logger.info(f"[Response] Status={resp.status_code} Body={resp.text[:200]}")

        resp.raise_for_status()
        data = resp.json()

        # normalize list of dicts
        if isinstance(data, dict):
            for k in ("results", "data", "rows"):
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break
            else:
                if all(isinstance(v, dict) for v in data.values()):
                    data = list(data.values())
                else:
                    return Response({"result": data})

        return Response(data)

    except requests.RequestException as e:
        logger.exception("Request to Wicket failed")
        return Response({"error": str(e)}, status=502)



# ---------- Charts ----------
class ChartViewSet(viewsets.ModelViewSet):
    serializer_class = ChartSerializer
    permission_classes = [IsAuthenticated]

    # ----------------------------------
    # QUERYSET (TENANT SAFE)
    # ----------------------------------
    def get_queryset(self):
        tenant = get_current_tenant()
        return Chart.objects.filter(tenant=tenant) if tenant else Chart.objects.none()

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            tenant=get_current_tenant(),
        )

    # ----------------------------------
    # RUNTIME EXECUTION
    # ----------------------------------
    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        dataset_id = request.data.get("dataset_id")
        if not dataset_id:
            return Response({"error": "dataset_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch dataset object
        try:
            dataset = Dataset.objects.get(pk=dataset_id)
        except Dataset.DoesNotExist:
            return Response({"error": "Dataset not found"}, status=status.HTTP_404_NOT_FOUND)

        # Run dataset (QB or other)
        result_response = self._run_dataset(dataset)

        # If the response is already an error Response, return it
        if isinstance(result_response, Response):
            return result_response

        # Extract data safely
        data = result_response.get("data", [])
        count = len(data) if isinstance(data, list) else 0
        fields = result_response.get("fields", [])
        entity = result_response.get("entity", "")

        # Ensure consistent empty chart payload
        if count == 0:
            chart_payload = {
                "entity": entity,
                "fields": fields,
                "count": 0,
                "data": [],
                "message": "No data returned for this dataset."
            }
        else:
            chart_payload = {
                "entity": entity,
                "fields": fields,
                "count": count,
                "data": data
            }

        return Response(chart_payload, status=status.HTTP_200_OK)

    def _run_dataset(self, dataset):
        """
        Executes a dataset against its data source.
        Supports QuickBooks (POST /query) and generic REST APIs.
        """
        source = dataset.api_source
        params = dataset.query_params.copy() if dataset.query_params else {}
        headers = {}
    
        # ---------------- QuickBooks ----------------
        if source.provider.lower() == "quickbooks":
            # Ensure credentials
            if not source.bearer_token or not source.base_url:
                return Response(
                    {"error": "QuickBooks access token or base URL missing."},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
            # Refresh token if expired
            if getattr(source, "oauth_token_expires_at", None) and source.oauth_token_expires_at <= timezone.now():
                try:
                    refresh_quickbooks_token(source)
                except requests.RequestException as e:
                    return Response(
                        {"error": f"Failed to refresh QuickBooks token: {str(e)}"},
                        status=status.HTTP_502_BAD_GATEWAY
                    )
    
            headers = {
                "Authorization": f"Bearer {source.bearer_token}",
                "Accept": "application/json",
                "Content-Type": "application/text",  # QB expects raw query in body
            }
    
            # Get entity & fields
            entity = getattr(dataset, "entity", None)
            fields = getattr(dataset, "fields", None)
    
            if not entity:
                return Response(
                    {"error": "QuickBooks entity must be selected."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not fields or not isinstance(fields, list) or len(fields) == 0:
                return Response(
                    {"error": "Select at least one field for QuickBooks entity."},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
            # Build query
            query = f"SELECT {', '.join(fields)} FROM {entity}"
            filters = getattr(dataset, "filters", {}) or {}
            where_clauses = []
    
            # Date range filter
            if filters.get("date_field") and filters.get("from") and filters.get("to"):
                where_clauses.append(
                    f"{filters['date_field']} BETWEEN '{filters['from']}' AND '{filters['to']}'"
                )
    
            # Equals filters
            for k, v in filters.get("equals", {}).items():
                where_clauses.append(f"{k} = '{v}'")
    
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
    
            url = f"{source.base_url}/query"
    
            # Debug logs
            print("[QB QUERY]", query)
            print("[QB URL]", url)
    
            try:
                resp = requests.post(url, data=query, headers=headers, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
                print("[QB RESPONSE]", payload)
            except requests.RequestException as e:
                return Response(
                    {"error": "QuickBooks request failed", "details": str(e), "query": query},
                    status=status.HTTP_502_BAD_GATEWAY
                )
    
            # Check QuickBooks logical errors
            if "Fault" in payload:
                return Response(
                    {"error": "QuickBooks API error", "details": payload["Fault"], "query": query},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
            query_response = payload.get("QueryResponse", {})
            if not query_response:
                return Response({
                    "entity": entity,
                    "fields": fields,
                    "count": 0,
                    "data": []
                })
    
            # Extract rows (QB returns key by entity name)
            entity_key = next(iter(query_response.keys()), None)
            rows = query_response.get(entity_key, []) if entity_key else []
    
            return Response({
                "entity": entity,
                "fields": fields,
                "count": len(rows),
                "data": rows,
            })
    
        # ---------------- Generic REST APIs ----------------
        else:
            url = urljoin(
                source.base_url.rstrip("/") + "/",
                (dataset.endpoint or "").lstrip("/")
            )
    
            if source.auth_type == "API_KEY_HEADER" and source.api_key:
                headers[source.api_key_header] = source.api_key
            elif source.auth_type == "BEARER" and source.api_key:
                headers["Authorization"] = f"Bearer {source.api_key}"
            elif source.auth_type == "API_KEY_QUERY" and source.api_key:
                params[source.api_key_header] = source.api_key
    
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    
            # Flatten standard API responses
            if isinstance(data, dict):
                for k in ("results", "data", "rows"):
                    if k in data and isinstance(data[k], list):
                        data = data[k]
                        break
    
            return Response({"data": data})

    # ----------------------------------
    # DATASET + AGGREGATION ENGINE
    # ----------------------------------
    def _get_value(self, row, field):
        """
        Supports dot-notation fields like 'CustomerRef.name'
        """
        if not field or not isinstance(row, dict):
            return None
    
        val = row
        for part in field.split("."):
            if not isinstance(val, dict):
                return None
            val = val.get(part)
        return val
    
    
    def _execute_dataset_with_aggregation(self, chart):
        # ----------------------------
        # Run dataset (SAFE)
        # ----------------------------
        dv = DatasetViewSet()
        dv.request = self.request
        dv.format_kwarg = None
    
        response = dv._run_dataset(chart.dataset)
    
        if not isinstance(response, Response):
            return Response({"type": "dataset", "data": []})
    
        payload = response.data
    
        # Normalize rows
        if isinstance(payload, dict):
            rows = payload.get("data", [])
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []
    
        if not rows:
            return Response({"type": "dataset", "data": []})
    
        x_field = chart.x_field
        y_field = chart.y_field
        agg = chart.aggregation or "none"
    
        # ----------------------------
        # NO AGGREGATION
        # ----------------------------
        if agg == "none":
            return Response({"type": "dataset", "data": rows})
    
        # ----------------------------
        # AGGREGATION
        # ----------------------------
        buckets = defaultdict(list)
    
        for row in rows:
            x_val = self._get_value(row, x_field)
    
            if x_val in (None, ""):
                continue
    
            if agg == "count":
                buckets[x_val].append(1)
                continue
    
            y_val = self._get_value(row, y_field)
    
            try:
                y_val = float(y_val)
            except (TypeError, ValueError):
                continue
    
            buckets[x_val].append(y_val)
    
        result = []
    
        for x_val, values in buckets.items():
            if not values:
                continue
    
            if agg == "count":
                y_val = len(values)
            elif agg == "avg":
                y_val = sum(values) / len(values)
            elif agg == "min":
                y_val = min(values)
            elif agg == "max":
                y_val = max(values)
            else:  # sum
                y_val = sum(values)
    
            result.append({
                x_field: x_val,
                y_field or "value": round(y_val, 2),
            })
    
        return Response({"type": "dataset", "data": result})
        
# ---------- Dashboards ----------
class DashboardViewSet(viewsets.ModelViewSet):
    serializer_class = DashboardSerializer
    permission_classes = [IsAuthenticated]

    # ---------- Tenant-aware queryset ----------
    def get_queryset(self):
        tenant = get_current_tenant()
        user = self.request.user
        show_deleted = self.request.query_params.get("include_deleted")
    
        qs = Dashboard.objects.filter(
            tenant=tenant
        ).filter(
            Q(created_by=user) |
            Q(groups__users=user)
        ).distinct()
    
        if show_deleted == "true":
            return qs.filter(is_deleted=True)
    
        return qs.filter(is_deleted=False)

    # ---------- Assign tenant on creation with limit enforcement ----------
    def perform_create(self, serializer):
        tenant = get_current_tenant()
        if not tenant:
            raise PermissionDenied("Tenant not detected. Cannot create dashboard.")

        # Enforce dashboard subscription limit
        enforce_subscription_limit(tenant, resource="dashboards")

        # Proceed normally
        serializer.save(created_by=self.request.user, tenant=tenant)

    # ---------- Tenant-aware single object ----------
    def get_object(self):
        tenant = get_current_tenant()
        obj = get_object_or_404(Dashboard, pk=self.kwargs["pk"], tenant=tenant)
        return obj

    # ---------- Add chart to dashboard ----------
    @action(detail=True, methods=["post"])
    def add_chart(self, request, pk=None):
        dashboard = self.get_object()
        chart_id = request.data.get("chart_id")
        layout = request.data.get("layout", {})
        order = request.data.get("order", 0)

        tenant = get_current_tenant()
        chart = get_object_or_404(Chart, pk=chart_id, tenant=tenant)

        dc, created = DashboardChart.objects.get_or_create(
            dashboard=dashboard,
            chart=chart,
            defaults={"layout": layout, "order": order},
        )
        if not created:
            dc.layout = layout
            dc.order = order
            dc.save()

        return Response(DashboardChartSerializer(dc).data)

    # 🔥 QB DASHBOARD EXECUTION
    @action(detail=True, methods=["get"])
    def run(self, request, pk=None):
        dashboard = self.get_object()
        slicers = request.query_params.dict()
        charts_payload = []
    
        for dc in dashboard.dashboard_charts.all().order_by("order"):
            chart = dc.chart
    
            # ---------- Excel charts ----------
            if chart.excel_data:
                charts_payload.append({
                    "id": chart.id,
                    "name": chart.name,
                    "type": chart.chart_type,
                    "xField": chart.x_field,
                    "yField": chart.y_field,
                    "stackedFields": chart.stacked_fields or [],
                    "filters": chart.filters or {},
                    "selectedFields": chart.selected_fields,
                    "data": chart.excel_data,
                })
                continue
    
            # ---------- QuickBooks Dataset ----------
            if chart.dataset:
                dataset = chart.dataset
    
                # Merge slicers into dataset filters
                merged_filters = dataset.filters.copy() if dataset.filters else {}
    
                if slicers.get("from") and slicers.get("to") and slicers.get("date_field"):
                    merged_filters.update({
                        "date_field": slicers["date_field"],
                        "from": slicers["from"],
                        "to": slicers["to"],
                    })
    
                equals = merged_filters.get("equals", {})
                for k, v in slicers.items():
                    if k in ("from", "to", "date_field"):
                        continue
                    equals[k] = v
                merged_filters["equals"] = equals
                dataset.filters = merged_filters
    
                try:
                    cv = ChartViewSet()
                    cv.request = request
                    cv.format_kwarg = None
    
                    # --------------------
                    # 1️⃣ Fetch raw rows from QB / dataset
                    # --------------------
                    raw_rows = cv._execute_dataset_raw(chart)
    
                    # Debug: check raw rows
                    print(f"[DEBUG] Chart {chart.id} raw rows: {raw_rows[:3]}")  # first 3 rows
    
                    # --------------------
                    # 2️⃣ Apply calculated fields, logic rules, filters
                    # --------------------
                    rows = transform_rows_safe(
                        raw_rows,
                        calculated_fields=getattr(chart, "calculated_fields", []),
                        logic_rules=getattr(chart, "logic_rules", []),
                        logic_expression=getattr(chart, "logic_expression", None),
                        filters=chart.filters,
                    )
    
                    # Debug: check transformed rows
                    print(f"[DEBUG] Chart {chart.id} transformed rows: {rows[:3]}")
    
                    # --------------------
                    # 3️⃣ Aggregate rows for chart
                    # --------------------
                    rows = cv._aggregate_rows_for_chart(chart, rows)
    
                    # --------------------
                    # 4️⃣ Optional: Apply transform again if aggregation may alter fields
                    # --------------------
                    rows = transform_rows_safe(
                        rows,
                        calculated_fields=getattr(chart, "calculated_fields", []),
                        logic_rules=getattr(chart, "logic_rules", []),
                        logic_expression=getattr(chart, "logic_expression", None),
                        filters=chart.filters,
                    )
    
                except Exception as e:
                    print(f"[ERROR] Dashboard {dashboard.id}, chart {chart.id}: {e}")
                    rows = []
    
                charts_payload.append({
                    "id": chart.id,
                    "name": chart.name,
                    "type": chart.chart_type,
                    "xField": chart.x_field,
                    "yField": chart.y_field,
                    "stackedFields": chart.stacked_fields or [],
                    "filters": chart.filters or {},
                    "selectedFields": chart.selected_fields,
                    "data": rows,
                })
    
        return Response({
            "id": dashboard.id,
            "name": dashboard.name,
            "charts": charts_payload,
        })
        
    # ---------- Helper method for filtering rows ----------
    def _apply_filters(self, rows, filters):
        if not filters:
            return rows

        def check_row(row):
            # Text equality
            equals = filters.get("equals", {})
            for k, v in equals.items():
                if row.get(k) != v:
                    return False

            # Number / range filters
            for f in filters.get("range", []):
                val = row.get(f["field"])
                if val is None:
                    return False
                if f.get("min") is not None and val < f["min"]:
                    return False
                if f.get("max") is not None and val > f["max"]:
                    return False
            return True

        return [r for r in rows if check_row(r)]
        
    # ---------- Delete dashboard ----------
    def destroy(self, request, *args, **kwargs):
        dashboard = self.get_object()
        dashboard.is_deleted = True
        dashboard.save()

        return Response(
            {"success": True, "message": "Dataset moved to recycle bin"},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        tenant = get_current_tenant()

        try:
            dashboard = Dashboard.objects.get(
                pk=pk,
                tenant=tenant,
                is_deleted=True
            )
        except Dashboard.DoesNotExist:
            return Response(
                {"detail": "Dashboard not found or already active"},
                status=status.HTTP_404_NOT_FOUND
            )

        dashboard.is_deleted = False
        dashboard.save(update_fields=["is_deleted"])

        return Response(
            {"message": "Dashboard restored successfully"},
            status=status.HTTP_200_OK
        )
        
    @action(detail=True, methods=["delete"], url_path="hard_delete")
    def hard_delete(self, request, pk=None):
        tenant = get_current_tenant()

        try:
            dashboard = Dashboard.objects.get(
                pk=pk,
                tenant=tenant,
                is_deleted=True,  # must be soft-deleted first
            )
        except Dashboard.DoesNotExist:
            return Response(
                {"detail": "Dashboard not found or not in recycle bin"},
                status=status.HTTP_404_NOT_FOUND,
            )

        dashboard.delete()

        return Response(
            {
                "success": True,
                "message": "Dashboard permanently deleted"
            },
            status=status.HTTP_200_OK
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def support_request(request):
    user = request.user

    tenant = get_current_tenant()
    if not tenant:
        tenant_user = (
            TenantUser.objects
            .filter(user=user)
            .select_related("tenant")
            .first()
        )
        tenant = tenant_user.tenant if tenant_user else None

    name = request.data.get("name")
    email = request.data.get("email")
    message = request.data.get("message")

    if not message:
        return Response(
            {"error": "Message is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    subject = f"Support request from {name or user.email}"

    body = f"""
Support Request

Tenant: {tenant.name if tenant else "N/A"}
Tenant ID: {tenant.id if tenant else "N/A"}
User: {user.email}
Name: {name or "N/A"}
Email: {email or user.email}

Message:
{message}
"""

    try:
        email_msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=["support@darajatechnologies.ca"],
            reply_to=[email or user.email],
        )
        email_msg.send(fail_silently=False)

    except Exception as e:
        logging.exception("Support email failed")
        return Response(
            {"error": "Failed to send support email"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({"success": True})



@api_view(["POST"])
@permission_classes([AllowAny])
def support_guest(request):
    """
    Handle guest support requests from frontend.
    Expects JSON: { name, email, message }
    """
    data = request.data
    name = data.get("name", "Guest")
    email = data.get("email", "")
    message = data.get("message", "").strip()

    if not message:
        return Response({"error": "Message is required"}, status=status.HTTP_400_BAD_REQUEST)

    # Use guest fallback if email not provided
    reply_to_email = email if email else settings.DEFAULT_FROM_EMAIL

    subject = f"Support request from {name}"
    body = f"""
Support Request

Name: {name}
Email: {email or 'N/A'}

Message:
{message}
"""

    try:
        email_msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=["support@darajatechnologies.ca"],
            reply_to=[reply_to_email],
        )
        email_msg.send(fail_silently=False)

    except Exception as e:
        logging.exception("Support email failed")
        return Response({"error": "Failed to send support email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({"success": True})




    

