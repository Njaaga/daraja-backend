from django.apps import apps
from django.db import models
from .models import Tenant, get_current_tenant

def patch_all_models():
    for model in apps.get_models():
        # Skip built-in apps
        if model._meta.app_label in ['auth', 'contenttypes', 'sessions', 'admin']:
            continue

        if model.__name__ == "Tenant":
            continue

        if not hasattr(model, 'tenant'):
            field = models.ForeignKey(
                Tenant,
                on_delete=models.CASCADE,
                null=True,
                blank=True,
                related_name=f'{model._meta.model_name}_set'
            )
            field.contribute_to_class(model, 'tenant')

        # Patch save to auto-set tenant
        original_save = model.save

        def save_with_tenant(self, *args, **kwargs):
            if not getattr(self, 'tenant', None):
                self.tenant = get_current_tenant()
            return original_save(self, *args, **kwargs)

        model.save = save_with_tenant
