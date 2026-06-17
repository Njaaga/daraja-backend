from django.db import models
from semantic.models import BusinessModel
from tenants.models import Tenant

class Metric(models.Model):

    AGGREGATIONS = [
        ("sum", "Sum"),
        ("avg", "Average"),
        ("count", "Count"),
        ("max", "Max"),
        ("min", "Min"),
    ]

    business_model = models.ForeignKey(
        BusinessModel,
        on_delete=models.CASCADE,
        related_name="metrics"
    )

    name = models.CharField(max_length=255)

    dataset = models.CharField(max_length=255)

    field_name = models.CharField(max_length=255)

    aggregation = models.CharField(
        max_length=50,
        choices=AGGREGATIONS
    )

    formula = models.JSONField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name

class MetricSnapshot(models.Model):

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="metric_snapshots"
    )

    metric = models.ForeignKey(
        "metrics.Metric",
        on_delete=models.CASCADE,
        related_name="snapshots"
    )

    value = models.FloatField(
        default=0
    )

    recorded_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self):
        return (
            f"{self.metric.name} - "
            f"{self.value} - "
            f"{self.recorded_at}"
        )
