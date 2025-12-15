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
from subscriptions.utils.subscription_limits import get_active_subscription, has_reached_limit
from django.db.models import Q
from .permissions import IsSuperAdmin



# ---------------------------
# USERS
# ---------------------------
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        tenant = get_current_tenant()
        if tenant:
            return User.objects.filter(tenantuser__tenant=tenant)
        return User.objects.none()

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        user = serializer.save()
        TenantUser.objects.get_or_create(user=user, tenant=tenant)

    # ---------- Single invite ----------
    @action(detail=False, methods=["post"])
    def invite(self, request):
        tenant = get_current_tenant()
        first_name = request.data.get("first_name", "")
        last_name = request.data.get("last_name", "")
        email = request.data.get("email")

        if not email:
            return Response({"error": "Email required"}, status=400)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
            },
        )

        # Link to tenant
        TenantUser.objects.get_or_create(user=user, tenant=tenant)

        # Generate token
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.FRONTEND_URL}/set-password?uid={uid}&token={token}"

        # Send invitation email
        send_mail(
            subject="Set your password",
            message=f"Hello {user.first_name},\n\nSet your password by clicking this link:\n{link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )

        return Response({"message": "Invitation sent", "status": "pending", "uid": uid, "token": token})

    # ---------- Bulk invite ----------
    @action(detail=False, methods=["post"])
    def bulk_invite(self, request):
        tenant = get_current_tenant()
        users_data = request.data.get("users", [])
        created_users = []

        for u in users_data:
            first_name = u.get("first_name")
            last_name = u.get("last_name")
            email = u.get("email")

            if first_name and last_name and email:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "username": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "is_active": True,
                    },
                )

                # Link to tenant
                TenantUser.objects.get_or_create(user=user, tenant=tenant)

                # Generate token
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                link = f"{settings.FRONTEND_URL}/set-password?uid={uid}&token={token}"

                # Send invitation email
                send_mail(
                    subject="Set your password",
                    message=f"Hello {user.first_name},\n\nSet your password by clicking this link:\n{link}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                )

                user_data = UserSerializer(user).data
                user_data.update({"uid": uid, "token": token})
                created_users.append(user_data)

        return Response(
            {"message": f"{len(created_users)} users invited successfully", "users": created_users},
            status=status.HTTP_201_CREATED
        )

    # ---------- Delete user ----------
    def destroy(self, request, *args, **kwargs):
        self.get_object()  # Ensures tenant filtering
        return super().destroy(request, *args, **kwargs)

    # ---------- Current user info ----------
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        user = request.user
        data = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
        return Response(data)
    
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
        return Group.objects.filter(tenant=tenant) if tenant else Group.objects.none()

    def get_serializer_class(self):
        if self.request.method in ["GET"]:
            return GroupNestedSerializer
        return GroupSerializer

    def perform_create(self, serializer):
        tenant = get_current_tenant()
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



# ---------- Data Sources ----------
class ApiDataSourceViewSet(viewsets.ModelViewSet):
    serializer_class = ApiDataSourceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        return ApiDataSource.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        print("Current tenant:", tenant)  # Debug
        serializer.save(
            tenant=tenant,
            created_by=self.request.user
        )

    def get_object(self):
        tenant = get_current_tenant()
        obj = get_object_or_404(ApiDataSource, id=self.kwargs["pk"], tenant=tenant)
        return obj


# ---------- Datasets ----------
class DatasetViewSet(viewsets.ModelViewSet):
    """
    Tenant-aware ViewSet for managing datasets.
    """
    serializer_class = DatasetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        return Dataset.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = get_current_tenant()
        serializer.save(
            created_by=self.request.user,
            tenant=tenant
        )

    def get_object(self):
        tenant = get_current_tenant()
        obj = get_object_or_404(Dataset, id=self.kwargs["pk"], tenant=tenant)
        return obj

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

# Ad-hoc run endpoint: POST /api/datasets/run/
from rest_framework.views import APIView
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
            return Response({"error": "api_source and endpoint required"}, status=status.HTTP_400_BAD_REQUEST)

        source = get_object_or_404(ApiDataSource, pk=source_id)
        # build a pseudo-dataset object
        dataset = Dataset(name="__adhoc__", api_source=source, endpoint=endpoint, query_params=params)
        return _run_dataset_and_respond(dataset, {})


def _run_dataset_and_respond(dataset, overrides):
    """
    Core runner: builds URL, applies auth, fetches data and returns JSON (list of dicts)
    """
    source = dataset.api_source
    endpoint = dataset.endpoint or ""
    # endpoint may be relative; join with base_url
    url = urljoin(source.base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    # params: start from dataset.query_params then overrides
    params = {}
    if dataset.query_params:
        params.update(dataset.query_params)
    params.update(overrides or {})

    headers = {}
    if source.auth_type == "API_KEY_HEADER" and source.api_key:
        headers[source.api_key_header] = source.api_key
    elif source.auth_type == "BEARER" and source.api_key:
        headers["Authorization"] = f"Bearer {source.api_key}"
    elif source.auth_type == "API_KEY_QUERY" and source.api_key:
        params.update({"api_key": source.api_key})

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # normalize: prefer list of dicts; if data has 'results' or 'data' keys, try to extract
        if isinstance(data, dict):
            for k in ("results", "data", "rows"):
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break
            else:
                # if dict of records, try convert
                # e.g., {id: {...}, ...} -> list
                if all(isinstance(v, dict) for v in data.values()):
                    data = list(data.values())
                else:
                    # Can't reliably convert - return the dict directly
                    return Response({"result": data})
        return Response(data)
    except requests.RequestException as e:
        return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


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

    # ---------- Assign tenant on creation ----------
    def perform_create(self, serializer):
        tenant = get_current_tenant()

        # ---- 1. Get active subscription ----
        sub = get_active_subscription()

        if not sub:
            return Response(
                {"error": "No active subscription. Please subscribe to a plan."},
                status=403,
            )

        # ---- 2. Count dashboards ----
        dashboard_count = Dashboard.objects.filter(tenant=tenant).count()
        max_dashboards = sub.plan.max_dashboards

        # ---- 3. Enforce limit ----
        if has_reached_limit(dashboard_count, max_dashboards):
            raise PermissionDenied(
                f"Dashboard limit reached ({max_dashboards}). Upgrade your plan."
            )

        # ---- 4. Proceed normally ----
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