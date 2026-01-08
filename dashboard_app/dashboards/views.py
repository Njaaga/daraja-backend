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



# ---------------------------
# USERS
# ---------------------------
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    # -----------------------------
    # Queryset (active by default)
    # -----------------------------
    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return User.objects.none()

        qs = User.objects.filter(tenantuser__tenant=tenant)

        include_deleted = self.request.query_params.get("include_deleted")
        if include_deleted != "true":
            qs = qs.filter(is_active=True)

        return qs.order_by("first_name", "last_name")

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
    authentication_classes = []  # bypass JWT

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

        qs = Group.objects.filter(tenant=tenant)

        # Allow restore & hard delete to access deleted records
        if self.action in ["restore", "hard_delete"]:
            return qs

        # Recycle bin view
        if self.request.query_params.get("recycle") == "true":
            return qs.filter(is_deleted=True)

        # Default: active only
        return qs.filter(is_deleted=False)



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
        return qs.filter(is_deleted=show_deleted) if show_deleted else qs.filter(is_deleted=False)

    def get_object(self):
        tenant = get_current_tenant()
        return get_object_or_404(
            ApiDataSource,
            id=self.kwargs["pk"],
            tenant=tenant
        )

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        enforce_subscription_limit(tenant, "datasources")

        serializer.save(
            tenant=tenant,
            created_by=self.request.user
        )

    # ♻️ Soft delete
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.is_deleted = True
        obj.save(update_fields=["is_deleted"])

        return Response(
            {"success": True, "message": "API source moved to recycle bin"},
            status=status.HTTP_200_OK
        )

    # ♻️ Restore
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        tenant = get_current_tenant()
        obj = get_object_or_404(
            ApiDataSource.objects.filter(tenant=tenant),
            id=pk
        )
        obj.is_deleted = False
        obj.save(update_fields=["is_deleted"])

        return Response(
            {"success": True, "message": "API source restored"}
        )



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
            query_params=query_params
        )
        return self._run_dataset(dataset)

    # ---------- Internal Dataset Runner ----------
    def _run_dataset(self, dataset):
        source = dataset.api_source
        endpoint = dataset.endpoint or ""
        url = urljoin(source.base_url.rstrip("/") + "/", endpoint.lstrip("/"))

        params = dataset.query_params or {}
        headers = {}

        # Handle API auth types
        if source.auth_type == "API_KEY_HEADER" and source.api_key:
            headers[source.api_key_header] = source.api_key
        elif source.auth_type == "BEARER" and source.api_key:
            headers["Authorization"] = f"Bearer {source.api_key}"
        elif source.auth_type == "API_KEY_QUERY" and source.api_key:
            params.update({source.api_key_header: source.api_key})

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # Normalize response to list of dicts
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

            return Response({"data": data})

        except requests.RequestException as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        

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
        Body: { api_source: <id>, endpoint: "/path", query_params: {..} }
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

        return run_dataset_wicket(dataset)


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

    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant:
            return Chart.objects.filter(tenant=tenant)
        return Chart.objects.none()

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                print("VALIDATION ERRORS:", serializer.errors)
                return Response(serializer.errors, status=400)

            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=201, headers=headers)

        except Exception as e:
            import traceback
            print("UNEXPECTED ERROR:", str(e))
            traceback.print_exc()
            return Response({"error": str(e)}, status=400)


    def perform_create(self, serializer):
        tenant = get_current_tenant()
        serializer.save(created_by=self.request.user, tenant=tenant)

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        chart = self.get_object()

        # Excel chart
        if chart.excel_data:
            return Response({"data": chart.excel_data})

        # Multi-dataset joins
        if chart.joins.exists():
            return self._run_chart_with_joins(chart)

        # Single dataset
        if chart.dataset:
            return self._run_dataset(chart.dataset)

        return Response(
            {"error": "Chart has no dataset, joins, or Excel data."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------
    # Internal helpers
    # ------------------------
    def _run_dataset(self, dataset):
        dv = DatasetViewSet()
        dv.request = self.request
        dv.format_kwarg = None
        return dv._run_dataset(dataset)

    def _run_chart_with_joins(self, chart):
        joins = chart.joins.all()
        if not joins:
            return Response({"error": "No joins found"}, status=400)

        tenant = get_current_tenant()
        datasets = {}

        # Fetch datasets, filtered by tenant
        for join in joins:
            for ds in [join.left_dataset, join.right_dataset]:
                if ds.id not in datasets:
                    if ds.tenant != tenant:
                        continue  # skip datasets outside tenant
                    resp = self._run_dataset(ds)
                    if isinstance(resp.data, dict) and "data" in resp.data:
                        datasets[ds.id] = resp.data["data"]
                    else:
                        datasets[ds.id] = resp.data

        # Simple inner join for first join only
        join = joins[0]
        left_rows = datasets.get(join.left_dataset.id, [])
        right_rows = datasets.get(join.right_dataset.id, [])

        left_key = join.left_field
        right_key = join.right_field

        joined_data = []
        right_index = {r[right_key]: r for r in right_rows if right_key in r}

        for l in left_rows:
            key = l.get(left_key)
            if key in right_index:
                merged = {**l, **right_index[key]}
                joined_data.append(merged)

        return Response({"data": joined_data})

# ---------- Dashboards ----------
class DashboardViewSet(viewsets.ModelViewSet):
    serializer_class = DashboardSerializer
    permission_classes = [IsAuthenticated]

    # ---------- Tenant-aware queryset ----------
    def get_queryset(self):
        tenant = get_current_tenant()
        user = self.request.user
        if not tenant:
            return Dashboard.objects.none()

        # Only dashboards the user owns or was granted through groups
        return Dashboard.objects.filter(
            tenant=tenant
        ).filter(
            Q(created_by=user) |
            Q(groups__users=user)
        ).distinct()

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

    # ---------- Delete dashboard ----------
    def destroy(self, request, *args, **kwargs):
        self.get_object()  # ensures tenant filtering
        return super().destroy(request, *args, **kwargs)
    



