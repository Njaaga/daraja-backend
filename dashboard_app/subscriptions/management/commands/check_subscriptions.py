# subscriptions/management/commands/check_subscriptions.py
from django.core.management.base import BaseCommand
from subscriptions.models import TenantSubscription

class Command(BaseCommand):
    help = "Check all subscriptions for expiry and auto-renew"

    def handle(self, *args, **options):
        subs = TenantSubscription.objects.all()
        for sub in subs:
            sub.check_expiry()
        self.stdout.write(self.style.SUCCESS("Checked all subscriptions."))
