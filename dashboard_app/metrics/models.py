from django.db import models
from semantic.models import BusinessModel


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
