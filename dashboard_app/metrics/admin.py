from django.contrib import admin
from .models import MetricSnapshot


@admin.register(MetricSnapshot)
class MetricSnapshotAdmin(admin.ModelAdmin):

    list_display = (
        "metric",
        "tenant",
        "value",
        "recorded_at",
    )

    list_filter = (
        "tenant",
        "metric",
    )

    search_fields = (
        "metric__name",
    )
