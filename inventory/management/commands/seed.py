import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inventory.demo import import_catalog, simulate
from inventory.models import Customer, Product, Sale

SAMPLE_CUSTOMERS = [
    ('Nusrat Jahan', '01711-552301'), ('Rafiq Ahmed', '01819-224718'), ('Tania Akter', '01552-776102'),
    ('Mahmud Hasan', '01923-440019'), ('Sharmin Sultana', '01611-908871'), ('Arif Chowdhury', '01712-331045'),
    ('Farzana Rahman', '01815-660290'), ('Imran Hossain', '01716-118833'),
]

DAYS = 60


class Command(BaseCommand):
    help = (
        'Fill an empty database with the Shwapno product catalogue, suppliers, customers '
        f'and {DAYS} days of purchases, sales and adjustments. Does nothing if data already exists.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if Sale.objects.exists() or Product.objects.exists():
            self.stdout.write('The database already has products or sales — nothing to seed. '
                              'Use "import_catalog" to add the Shwapno products to it.')
            return
        rng = random.Random(42)
        midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight - timedelta(days=DAYS)
        products = import_catalog(rng, start - timedelta(minutes=1))
        customers = [Customer.objects.create(name=n, phone=p) for n, p in SAMPLE_CUSTOMERS]
        orders = simulate(products, customers, start, rng)
        self.stdout.write(self.style.SUCCESS(
            f'Added {len(products)} products, {len(customers)} customers and {orders} sales over {DAYS} days.'
        ))
