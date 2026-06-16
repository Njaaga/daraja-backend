from django.db import models
from metrics.models import Metric


class KPI(models.Model):

    metric = models.ForeignKey(
        Metric,
        on_delete=models.CASCADE,
        related_name="kpis"
    )

    name = models.CharField(max_length=255)

    target_value = models.DecimalField(
        max_digits=18,
        decimal_places=2
    )

    warning_threshold = models.DecimalField(
        max_digits=18,
        decimal_places=2
    )

    critical_threshold = models.DecimalField(
        max_digits=18,
        decimal_places=2
    )

    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(
        auto_now_add=True
    )
