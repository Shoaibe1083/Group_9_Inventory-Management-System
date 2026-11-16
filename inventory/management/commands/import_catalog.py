import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.demo import import_catalog, simulate
from inventory.models import Customer, Product


class Command(BaseCommand):
    help = (
        'Add the Shwapno product catalogue (inventory/data/shwapno_products.json) to the '
        'database, skipping products whose name already exists. With --demo-sales N, also '
        'simulates N days of sample sales and restocks across all products.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--demo-sales', type=int, default=0, metavar='DAYS',
                            help='Simulate this many days of sample trading after importing.')

    @transaction.atomic
    def handle(self, *args, demo_sales=0, **options):
        rng = random.Random()
        midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=demo_sales)
        created = import_catalog(rng, start - timedelta(minutes=1) if demo_sales else timezone.now())
        self.stdout.write(self.style.SUCCESS(f'Imported {len(created)} new products.'))
        if demo_sales:
            orders = simulate(list(Product.objects.all()), list(Customer.objects.all()), start, rng)
            self.stdout.write(self.style.SUCCESS(f'Simulated {orders} sales over {demo_sales} days.'))
