# dashboards/admin.py
from django.contrib import admin
from .models import ApiDataSource, Dataset, Chart, Dashboard, DashboardChart

@admin.register(ApiDataSource)
class ApiDataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "base_url", "auth_type", "created_by", "created_at")
    readonly_fields = ("created_by", "created_at")

@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "api_source", "endpoint", "created_by", "created_at")

@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset", "chart_type", "created_by", "created_at")

@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at")

@admin.register(DashboardChart)
class DashboardChartAdmin(admin.ModelAdmin):
    list_display = ("dashboard", "chart", "order")
