from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField


class ApiDataSource(models.Model):
    # ----------------------------
    # Providers
    # ----------------------------
    PROVIDERS = [
        ("generic", "Generic API"),
        ("quickbooks", "QuickBooks Online"),
    ]

    # ----------------------------
    # Authentication Types
    # ----------------------------
    AUTH_TYPES = [
        ("NONE", "None"),
        ("API_KEY_HEADER", "API Key (Header)"),
        ("API_KEY_QUERY", "API Key (Query Param)"),
        ("BEARER", "Bearer Token"),
        ("JWT_HS256", "JWT (HS256)"),
        ("OAUTH2", "OAuth 2.0"),
    ]

    # ----------------------------
    # Core metadata
    # ----------------------------
    name = models.CharField(max_length=255)
    provider = models.CharField(
        max_length=32,
        choices=PROVIDERS,
        default="generic",
        db_index=True
    )

    base_url = models.URLField(
        help_text="Base API URL (no trailing slash)"
    )

    auth_type = models.CharField(
        max_length=32,
        choices=AUTH_TYPES,
        default="NONE"
    )

    # ----------------------------
    # API Key authentication
    # ----------------------------
    api_key = models.TextField(blank=True)
    api_key_name = models.CharField(
        max_length=255,
        default="Authorization",
        help_text="Header or query parameter name"
    )

    # ----------------------------
    # Static Bearer authentication
    # (Generic APIs only)
    # ----------------------------
    bearer_token = models.TextField(blank=True)
    bearer_prefix = models.CharField(
        max_length=32,
        default="Bearer"
    )

    # ----------------------------
    # JWT (HS256)
    # ----------------------------
    jwt_secret = models.TextField(blank=True, null=True)
    jwt_subject = models.CharField(max_length=255, blank=True, null=True)
    jwt_audience = models.CharField(max_length=255, blank=True, null=True)
    jwt_issuer = models.CharField(max_length=255, blank=True, null=True)
    jwt_ttl_seconds = models.PositiveIntegerField(default=300)

    # ----------------------------
    # OAuth 2.0 (QuickBooks, future providers)
    # ----------------------------
    oauth_access_token = models.TextField(blank=True, null=True)
    oauth_refresh_token = models.TextField(blank=True, null=True)
    oauth_token_expires_at = models.DateTimeField(blank=True, null=True)

    # QuickBooks-specific
    realm_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="QuickBooks company (realm) ID"
    )

    # ----------------------------
    # Optional provider headers
    # ----------------------------
    extra_headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional provider-specific headers (e.g. minorversion)"
    )

    # ----------------------------
    # Ownership & lifecycle
    # ----------------------------
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="api_sources",
        null=True,
        blank=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(default=timezone.now)

    # Soft delete
    is_deleted = models.BooleanField(default=False)

    # ----------------------------
    # Meta
    # ----------------------------
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "is_deleted"]),
            models.Index(fields=["provider"]),
        ]

    # ----------------------------
    # Helpers
    # ----------------------------
    def save(self, *args, **kwargs):
        if self.base_url:
            self.base_url = self.base_url.rstrip("/")
        super().save(*args, **kwargs)

    def is_oauth(self):
        return self.auth_type == "OAUTH2"

    def is_quickbooks(self):
        return self.provider == "quickbooks"

    def token_expired(self):
        return (
            self.oauth_token_expires_at
            and timezone.now() >= self.oauth_token_expires_at
        )

    def __str__(self):
        return f"{self.name} ({self.provider})"
        


class Dataset(models.Model):
    name = models.CharField(max_length=255)

    api_source = models.ForeignKey(
        ApiDataSource,
        on_delete=models.CASCADE,
        related_name="datasets"
    )

    # 🔹 GENERIC MODE (what you already have)
    endpoint = models.CharField(max_length=1024, blank=True)
    query_params = models.JSONField(default=dict, blank=True)

    # 🔹 SEMANTIC MODE (for QuickBooks & future BI)
    entity = models.CharField(max_length=100, blank=True)     # Invoice, Customer
    fields = models.JSONField(default=list, blank=True)       # ["Id", "TotalAmt"]
    filters = models.JSONField(default=dict, blank=True)      # dates, status, etc.

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    is_deleted = models.BooleanField(default=False)


    def __str__(self):
        return self.name



JOIN_TYPE_CHOICES = [
    ("inner", "Inner"),
    ("left", "Left"),
    ("right", "Right"),
]

# ------------------------------
# Chart model
# ------------------------------
class Chart(models.Model):
    CHART_TYPES = [
        ("bar", "Bar"),
        ("line", "Line"),
        ("pie", "Pie"),
        ("kpi", "KPI"),
        ("table", "Table"),
        ("stacked_bar", "Stacked Bar"),
        ("area", "Area"),
        ("scatter", "Scatter"),
    ]

    AGGREGATION_CHOICES = [
        ("sum", "Sum"),
        ("avg", "Average"),
        ("min", "Min"),
        ("max", "Max"),
        ("count", "Count"),
        ("none", "None"),   # For table charts with no aggregation
    ]

    name = models.CharField(max_length=255)
    dataset = models.ForeignKey(
        "Dataset", on_delete=models.SET_NULL, null=True, blank=True
    )
    chart_type = models.CharField(max_length=50, choices=CHART_TYPES)
    x_field = models.CharField(max_length=255, null=True, blank=True)
    y_field = models.CharField(max_length=255, null=True, blank=True)
    aggregation = models.CharField(
        max_length=50, choices=AGGREGATION_CHOICES, default="none"
    )
    excel_data = models.JSONField(null=True, blank=True)
    filters = models.JSONField(null=True, blank=True)
    logic_rules = models.JSONField(null=True, blank=True)
    logic_expression = models.TextField(null=True, blank=True)
    selected_fields = models.JSONField(null=True, blank=True)  # For table charts
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Keep this field as JSON, no conflict with ChartJoin
    joins = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.name


# ------------------------------
# ChartJoin model
# ------------------------------
class ChartJoin(models.Model):
    chart = models.ForeignKey(
        'Chart',
        on_delete=models.CASCADE,
        related_name='chart_joins',
        null=True,
        blank=True  # optional, allows form serializers to omit it
    )

    left_dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='left_joins', 
        null=True,
        blank=True
    )
    
    left_field = models.CharField(
        max_length=255, 
        null=True, 
        blank=True)
    
    right_dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='right_joins',
        null=True,
        blank=True
    )
    
    right_field = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    on_condition = models.CharField(max_length=512, blank=True, null=True)
    type = models.CharField(max_length=10, choices=JOIN_TYPE_CHOICES, default="inner")



    
class Dashboard(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    charts = models.ManyToManyField(Chart, through="DashboardChart", related_name="dashboards")
    
    # 🔥 recycle bin
    is_deleted = models.BooleanField(default=False)
    def __str__(self):
        return self.name


class DashboardChart(models.Model):
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="dashboard_charts")
    chart = models.ForeignKey(Chart, on_delete=models.CASCADE)
    # layout meta to persist position/size in the grid (x,y,w,h)
    layout = models.JSONField(default=dict, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        unique_together = ("dashboard", "chart")

    def __str__(self):
        return f"{self.dashboard.name} - {self.chart.name}"
    

class Group(models.Model):
    name = models.CharField(max_length=255)
    users = models.ManyToManyField(User, blank=True, related_name="dashboard_groups")
    dashboards = models.ManyToManyField(Dashboard, blank=True, related_name="groups")

    # ✅ Recycle bin fields
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save()

    def __str__(self):
        return self.name
