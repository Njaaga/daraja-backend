# tenants/apps.py
from django.apps import AppConfig

class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'

    def ready(self):
        from . import tenant_patch
        tenant_patch.patch_all_models()
