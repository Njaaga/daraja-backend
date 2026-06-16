from django.db import models
from tenants.models import Tenant
from dashboards.models import Dataset


class BusinessModel(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="business_models"
    )

    name = models.CharField(max_length=255)

    description = models.TextField(blank=True)

    datasets = models.ManyToManyField(
        Dataset,
        related_name="business_models"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.name
