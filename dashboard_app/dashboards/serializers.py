from django.contrib.auth.models import User
from rest_framework import serializers
from .models import ApiDataSource, Dataset, Chart, Dashboard, DashboardChart, Group, ChartJoin
from django.contrib.auth import get_user_model
from tenants.models import Tenant  # your tenant model
import uuid

User = get_user_model()

class TenantSignupSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match")
        if User.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError("Username already exists")
        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError("Email already exists")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        
        # 1️⃣ Create tenant
        tenant = Tenant.objects.create(name=validated_data['company_name'])
        
        # 2️⃣ Create user linked to tenant
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            tenant=tenant  # assuming your User model has a tenant FK
        )
        
        # 3️⃣ (Optional) create schema or initialize tenant-specific data
        tenant.setup_schema()  # If you have a method for tenant DB/schema setup
        
        return user
    
# ----------------------------------------------------
# USER SERIALIZER
# ----------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_superuser",
        ]
        extra_kwargs = {
            "username": {"required": False},
            "is_active": {"read_only": True},
            "is_superuser": {"read_only": True},
        }






# ----------------------------------------------------
# SET PASSWORD SERIALIZER
# ----------------------------------------------------
class SetPasswordSerializer(serializers.Serializer):
    uid = serializers.IntegerField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=6)


# ----------------------------------------------------
# API DATA SOURCE SERIALIZER
# ----------------------------------------------------
class ApiDataSourceSerializer(serializers.ModelSerializer):
    # 🔒 Write-only secrets
    api_key = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    bearer_token = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    jwt_secret = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    # 🏢 Tenant info (read-only)
    tenant_id = serializers.PrimaryKeyRelatedField(
        source="tenant",
        read_only=True
    )
    tenant_name = serializers.CharField(
        source="tenant.name",
        read_only=True
    )

    class Meta:
        model = ApiDataSource
        fields = [
            "id",
            "name",
            "base_url",
            "auth_type",

            # API Key auth
            "api_key",
            "api_key_name",

            # Bearer auth
            "bearer_token",

            # JWT auth
            "jwt_secret",
            "jwt_subject",
            "jwt_audience",
            "jwt_issuer",
            "jwt_ttl_seconds",

            # Metadata
            "created_by",
            "created_at",
            "tenant_id",
            "tenant_name",
            "provider",           # 🔥 Add this
            "realm_id",           # Optional for QB
        ]
        read_only_fields = [
            "created_by",
            "created_at",
            "tenant_id",
            "tenant_name",
        ]

    # ------------------------------------------------------------------
    # 🔍 Validation
    # ------------------------------------------------------------------
    def validate(self, attrs):
        auth_type = attrs.get(
            "auth_type",
            self.instance.auth_type if self.instance else None
        )

        def existing(field):
            return getattr(self.instance, field, None) if self.instance else None

        if auth_type in ("API_KEY_HEADER", "API_KEY_QUERY"):
            if not (attrs.get("api_key") or existing("api_key")):
                raise serializers.ValidationError({
                    "api_key": "API key is required for this auth type."
                })

        elif auth_type == "BEARER":
            if not (attrs.get("bearer_token") or existing("bearer_token")):
                raise serializers.ValidationError({
                    "bearer_token": "Bearer token is required."
                })

        elif auth_type == "JWT_HS256":
            secret = attrs.get("jwt_secret") or existing("jwt_secret")
            subject = attrs.get("jwt_subject") or existing("jwt_subject")
            audience = attrs.get("jwt_audience") or existing("jwt_audience")

            missing = [
                name for name, value in {
                    "jwt_secret": secret,
                    "jwt_subject": subject,
                    "jwt_audience": audience,
                }.items()
                if not value
            ]

            if missing:
                raise serializers.ValidationError({
                    field: "This field is required for JWT auth."
                    for field in missing
                })

        return attrs

    # ------------------------------------------------------------------
    # 🛡️ Prevent wiping secrets on PATCH
    # ------------------------------------------------------------------
    def update(self, instance, validated_data):
        for secret_field in [
            "api_key",
            "bearer_token",
            "jwt_secret",
        ]:
            if secret_field not in validated_data:
                validated_data[secret_field] = getattr(instance, secret_field)

        return super().update(instance, validated_data)

    # ------------------------------------------------------------------
    # 🧩 Auto-attach tenant & creator
    # ------------------------------------------------------------------
    def create(self, validated_data):
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            validated_data.setdefault("created_by", request.user)
            validated_data.setdefault(
                "tenant",
                getattr(request.user, "tenant", None)
            )

        return super().create(validated_data)


# ----------------------------------------------------
# DATASET SERIALIZER
# ----------------------------------------------------
class DatasetSerializer(serializers.ModelSerializer):
    api_source_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "api_source",
            "api_source_name",
            "endpoint",
            "query_params",
            "entity",
            "fields",
            "filters",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]

    def get_api_source_name(self, obj):
        return obj.api_source.name if obj.api_source else None


class ChartJoinSerializer(serializers.ModelSerializer):
    left_dataset = serializers.PrimaryKeyRelatedField(
        queryset=Dataset.objects.all()
    )
    right_dataset = serializers.PrimaryKeyRelatedField(
        queryset=Dataset.objects.all()
    )

    class Meta:
        model = ChartJoin
        fields = [
            "id",
            "left_dataset",
            "left_field",
            "right_dataset",
            "right_field",
            "on_condition",
            "type",
        ]
        read_only_fields = ["id"]



# ----------------------------------------------------
# CHART SERIALIZER
class ChartSerializer(serializers.ModelSerializer):
    dataset_name = serializers.SerializerMethodField(read_only=True)

    joins = ChartJoinSerializer(many=True, required=False)
    excel_data = serializers.JSONField(required=False, allow_null=True)

    # Query definition fields (used at runtime)
    filters = serializers.JSONField(required=False, allow_null=True)
    logic_rules = serializers.JSONField(required=False, allow_null=True)
    logic_expression = serializers.CharField(required=False, allow_null=True)

    dataset = serializers.PrimaryKeyRelatedField(
        queryset=Dataset.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Chart
        fields = [
            "id",
            "name",
            "dataset",
            "dataset_name",
            "chart_type",
            "x_field",
            "y_field",
            "aggregation",
            "joins",
            "excel_data",
            "filters",
            "logic_rules",
            "logic_expression",
            "selected_fields",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["created_by", "created_at"]

    # ----------------------------
    # Derived fields
    # ----------------------------
    def get_dataset_name(self, obj):
        return obj.dataset.name if obj.dataset else None

    # ----------------------------
    # Validation
    # ----------------------------
    def validate(self, attrs):
        chart_type = attrs.get("chart_type")
        x_field = attrs.get("x_field")
        y_field = attrs.get("y_field")
        dataset = attrs.get("dataset")
        excel_data = attrs.get("excel_data")
    
        # ----------------------------
        # Excel-based charts
        # ----------------------------
        if excel_data is not None:
            if not isinstance(excel_data, list) or not excel_data:
                raise serializers.ValidationError(
                    "Excel charts require a non-empty excel_data array."
                )
    
            # Excel charts do not use dataset or joins
            return attrs
    
        # ----------------------------
        # API / Dataset-based charts
        # ----------------------------
        if not dataset:
            raise serializers.ValidationError(
                "Dataset is required for API-based charts."
            )
    
        # ----------------------------
        # Field requirements
        # ----------------------------
        if chart_type != "table":
            if not x_field or not y_field:
                raise serializers.ValidationError(
                    "x_field and y_field are required for this chart type."
                )
    
        return attrs


    # ----------------------------
    # Create
    # ----------------------------
    def create(self, validated_data):
        joins_data = validated_data.pop("joins", [])
        excel_data = validated_data.get("excel_data")

        # ----------------------------
        # Excel chart
        # ----------------------------
        if excel_data is not None:
            chart = Chart.objects.create(**validated_data)
            for join in joins_data:
                ChartJoin.objects.create(chart=chart, **join)
            return chart

        # ----------------------------
        # API / QuickBooks chart
        # ----------------------------
        if not validated_data.get("dataset") and joins_data:
            validated_data["dataset"] = joins_data[0]["left_dataset"]

        if not validated_data.get("dataset"):
            raise serializers.ValidationError(
                "Dataset is required for non-excel charts."
            )

        chart = Chart.objects.create(**validated_data)

        for join in joins_data:
            ChartJoin.objects.create(chart=chart, **join)

        return chart










# ----------------------------------------------------
# DASHBOARD CHART SERIALIZER  (must be ABOVE DashboardSerializer)
# ----------------------------------------------------
class DashboardChartSerializer(serializers.ModelSerializer):
    chart_detail = ChartSerializer(source="chart", read_only=True)

    class Meta:
        model = DashboardChart
        fields = ["id", "dashboard", "chart", "layout", "order", "chart_detail"]


# ----------------------------------------------------
# DASHBOARD SERIALIZER  (now it sees DashboardChartSerializer correctly)
# ----------------------------------------------------
class DashboardSerializer(serializers.ModelSerializer):
    # use DashboardChartSerializer for nested charts
    dashboard_charts = DashboardChartSerializer(many=True, read_only=True)
    
    # inbound payload: just list of chart IDs
    charts = serializers.ListField(write_only=True, required=False)

    class Meta:
        model = Dashboard
        fields = [
            "id",
            "name",
            "created_by",
            "created_at",
            "charts",            # inbound payload
            "dashboard_charts",  # nested serialized charts
        ]
        read_only_fields = ["created_by", "created_at"]

    def create(self, validated_data):
        charts_data = validated_data.pop("charts", [])
        dashboard = Dashboard.objects.create(**validated_data)

        # link charts
        for i, chart in enumerate(charts_data):
            DashboardChart.objects.create(
                dashboard=dashboard,
                chart_id=chart["chart"],
                layout=chart.get("layout", {}),
                order=chart.get("order", i),
            )

        return dashboard



# ----------------------------------------------------
# GROUP SERIALIZER
# ----------------------------------------------------
class GroupSerializer(serializers.ModelSerializer):
    dashboards = serializers.PrimaryKeyRelatedField(
        queryset=Dashboard.objects.all(), many=True, required=False
    )
    users = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), many=True, required=False
    )

    class Meta:
        model = Group
        fields = ["id", "name", "dashboards", "users"]

    def create(self, validated_data):
        dashboards = validated_data.pop("dashboards", [])
        users = validated_data.pop("users", [])
        group = Group.objects.create(**validated_data)
        group.dashboards.set(dashboards)
        group.users.set(users)
        return group

    def update(self, instance, validated_data):
        dashboards = validated_data.pop("dashboards", None)
        users = validated_data.pop("users", None)
        instance.name = validated_data.get("name", instance.name)
        instance.save()
        if dashboards is not None:
            instance.dashboards.set(dashboards)
        if users is not None:
            instance.users.set(users)
        return instance

# Nested serializers for read/display
class UserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]

class DashboardNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dashboard
        fields = ["id", "name"]

# Extend your GroupSerializer for read/display
class GroupNestedSerializer(GroupSerializer):
    dashboards = DashboardNestedSerializer(many=True, read_only=True)
    users = UserNestedSerializer(many=True, read_only=True)

