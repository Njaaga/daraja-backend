from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ApiDataSource(models.Model):
    AUTH_TYPES = [
        ("NONE", "None"),
        ("API_KEY_HEADER", "API Key (Header)"),
        ("API_KEY_QUERY", "API Key (Query Param)"),
        ("BEARER", "Bearer Token"),
        ("JWT_HS256", "JWT (HS256)"),
    ]

    name = models.CharField(max_length=255)
    base_url = models.URLField()
    auth_type = models.CharField(max_length=32, choices=AUTH_TYPES, default="NONE")

    # 🔐 API Key auth
    api_key = models.CharField(max_length=1024, blank=True)
    api_key_name = models.CharField(
        max_length=255,
        default="Authorization",
        help_text="Header name or query param name"
    )

    # 🔐 Bearer auth
    bearer_token = models.CharField(max_length=2048, blank=True)

    # 🔐 JWT auth (HS256)
    jwt_secret = models.CharField(max_length=1024, blank=True, null=True)
    jwt_subject = models.CharField(max_length=255, blank=True, null=True)
    jwt_audience = models.CharField(max_length=255, blank=True, null=True)
    jwt_issuer = models.CharField(max_length=255, blank=True, null=True)
    jwt_ttl_seconds = models.IntegerField(default=300)

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="api_sources",
        null=True,      # ✅ MUST be True for now
        blank=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(default=timezone.now)

    # ♻️ Soft delete
    is_deleted = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "is_deleted"]),
        ]
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Normalize base_url
        if self.base_url:
            self.base_url = self.base_url.rstrip("/")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name



class Dataset(models.Model):
    name = models.CharField(max_length=255)
    api_source = models.ForeignKey(
        ApiDataSource,
        on_delete=models.CASCADE,
        related_name="datasets"
    )
    endpoint = models.CharField(max_length=1024)
    query_params = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    # 🔥 recycle bin
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.name



class Chart(models.Model):
    CHART_TYPES = [
        ("bar", "Bar"),
        ("line", "Line"),
        ("pie", "Pie"),
        ("kpi", "KPI"),
        ("table", "Table"),
    ]

    AGGREGATION_CHOICES = [
        ("sum", "Sum"),
        ("avg", "Average"),
        ("min", "Min"),
        ("max", "Max"),
        ("count", "Count"),
        ("none", "None"),   # For table charts with no aggregation
    ]


    aggregation = models.CharField(
    max_length=50, 
    choices=AGGREGATION_CHOICES, 
    default="none"   # prevents null DB violations
    )

    
    name = models.CharField(max_length=255)
    dataset = models.ForeignKey(Dataset, on_delete=models.SET_NULL, null=True, blank=True)
    chart_type = models.CharField(max_length=50)
    x_field = models.CharField(max_length=255, null=True, blank=True)
    y_field = models.CharField(max_length=255, null=True, blank=True)
    aggregation = models.CharField(max_length=50, null=True, blank=True)
    excel_data = models.JSONField(null=True, blank=True)
    
    # NEW FIELDS
    filters = models.JSONField(null=True, blank=True)
    logic_rules = models.JSONField(null=True, blank=True)
    logic_expression = models.TextField(null=True, blank=True)

    created_by = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
JOIN_TYPE_CHOICES = [
    ("inner", "Inner"),
    ("left", "Left"),
    ("right", "Right"),
]

class ChartJoin(models.Model):
    chart = models.ForeignKey(
        'Chart',
        on_delete=models.CASCADE,
        related_name='joins',
        null=True,
        blank=True  # optional, allows form serializers to omit it
    )

    left_dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='left_joins'
    )
    left_field = models.CharField(max_length=255)
    right_dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='right_joins'
    )
    right_field = models.CharField(max_length=255)
    on_condition = models.CharField(max_length=512, blank=True, null=True)
    type = models.CharField(max_length=10, choices=JOIN_TYPE_CHOICES, default="inner")



    
class Dashboard(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    charts = models.ManyToManyField(Chart, through="DashboardChart", related_name="dashboards")

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