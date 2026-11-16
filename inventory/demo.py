"""Sample data used by the `seed` and `import_catalog` commands: the Shwapno
product catalogue (inventory/data/shwapno_products.json) and a sales
simulator that writes orders, purchases and write-offs straight into the
ledger in clock order, so every stock_after value is correct."""
import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.utils import timezone

from .models import Category, Order, Product, Sale, StockIn, StockMovement, Supplier
from .services import TWO_PLACES, next_codes

CATALOG_FILE = Path(__file__).resolve().parent / 'data' / 'shwapno_products.json'

SUPPLIERS = [
    # (name, phone, address, categories they supply)
    ('Bismillah Rice Agency', '01711-245890', 'Badamtoli, Dhaka', ['Rice', 'Dal & Lentils', 'Atta & Flour']),
    ('Rahman Traders', '01819-332716', 'Moulvibazar, Dhaka', ['Cooking Oil', 'Salt & Sugar', 'Spices', 'Sauces & Honey']),
    ('City Distributors', '01552-908144', 'Kawran Bazar, Dhaka', ['Personal Care', 'Cleaning']),
    ('Karim Wholesale', '01923-117405', 'Mirpur 1, Dhaka',
     ['Beverages', 'Chips & Snacks', 'Biscuits', 'Noodles & Pasta', 'Tea & Coffee', 'Dairy & Eggs']),
]


def load_catalog():
    return json.loads(CATALOG_FILE.read_text(encoding='utf-8'))['products']


def suppliers_by_category():
    mapping = {}
    for name, phone, address, categories in SUPPLIERS:
        supplier, _ = Supplier.objects.get_or_create(name=name, defaults={'phone': phone, 'address': address})
        for c in categories:
            mapping[c] = supplier
    return mapping


def import_catalog(rng, opening_date, user=None):
    """Create catalogue products that don't exist yet (matched by name), each
    with an estimated buy price and an opening-stock ledger row."""
    suppliers = suppliers_by_category()
    existing = {n.lower() for n in Product.objects.values_list('name', flat=True)}
    created = []
    for row in load_catalog():
        if row['name'].lower() in existing:
            continue
        category, _ = Category.objects.get_or_create(name=row['category'])
        price = Decimal(str(row['price']))
        # Shwapno doesn't publish buy prices: assume a 10–18% retail margin.
        cost = (price * Decimal(str(rng.uniform(0.82, 0.9)))).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        product = Product.objects.create(
            name=row['name'], category=category, supplier=suppliers.get(row['category']),
            price=price, cost_price=cost, quantity=0, low_stock_threshold=rng.choice([4, 5, 6, 8, 10]),
        )
        _, barcode = next_codes(product)
        product.sku = f'SW-{row["shwapno_sku"]}'
        product.barcode = barcode
        opening = rng.randint(15, 60)
        product.quantity = opening
        product.save(update_fields=['sku', 'barcode', 'quantity'])
        StockMovement.objects.create(
            product=product, kind='in', reason='opening', quantity=opening, stock_after=opening,
            unit_cost=cost, user=user, date=opening_date, note='Opening stock',
        )
        created.append(product)
    return created


def simulate(products, customers, start, rng, orders_per_day=(10, 18)):
    """Replay daily trading from `start` until now. A product only joins once
    its existing ledger has ended, so older history is never contradicted."""
    now = timezone.now()
    ready_at = {
        p.pk: StockMovement.objects.filter(product=p).order_by('-date').values_list('date', flat=True).first() or start
        for p in products
    }
    popularity = {p.pk: rng.choices([0, 1, 2, 3, 4, 6], weights=[1, 4, 5, 4, 3, 2])[0] for p in products}

    def log(product, qty, kind, reason, when, **extra):
        product.quantity += qty
        StockMovement.objects.create(
            product=product, kind=kind, reason=reason, quantity=qty,
            stock_after=product.quantity, date=when, **extra,
        )

    orders = 0
    day_start = timezone.localtime(start).replace(hour=0, minute=0, second=0, microsecond=0)
    while day_start <= now:
        live = [p for p in products if ready_at[p.pk] < day_start]
        restock_at = day_start + timedelta(hours=8, minutes=30)
        for p in live:
            if restock_at <= now and p.quantity <= p.low_stock_threshold + 3 and popularity[p.pk] and rng.random() < 0.5:
                qty = rng.randint(20, 48)
                entry = StockIn.objects.create(product=p, supplier=p.supplier, quantity=qty, unit_cost=p.cost_price)
                StockIn.objects.filter(pk=entry.pk).update(date=restock_at)
                log(p, qty, 'in', 'purchase', restock_at, unit_cost=p.cost_price, supplier=p.supplier, note='Weekly order')

        weekend = day_start.weekday() in (4, 5)  # Friday & Saturday are busier
        low, high = orders_per_day
        events = [
            (day_start + timedelta(hours=rng.randint(9, 21), minutes=rng.randint(0, 59), seconds=rng.randint(0, 59)), 'sale')
            for _ in range(rng.randint(low, high) + (5 if weekend else 0))
        ]
        if rng.random() < 0.15:
            events.append((day_start + timedelta(hours=20, minutes=45), 'writeoff'))

        for when, kind in sorted(events):
            if when > now:
                continue
            if kind == 'writeoff':
                candidates = [p for p in live if p.quantity > 2]
                if candidates:
                    p = rng.choice(candidates)
                    log(p, -rng.randint(1, 2), 'adjust', rng.choice(['damage', 'expired']), when,
                        unit_cost=p.cost_price, note='Found during shelf check')
                continue
            pool = [p for p in live for _ in range(popularity[p.pk]) if p.quantity > 0]
            if not pool:
                continue
            cart = {}
            for p in rng.sample(pool, k=min(len(pool), rng.randint(1, 5))):
                cart[p] = min(p.quantity, cart.get(p, 0) + rng.choice([1, 1, 1, 2, 2, 3]))
            subtotal = sum((p.price * q for p, q in cart.items()), Decimal('0'))
            discount = Decimal(rng.choice([0, 0, 0, 0, 10, 20, 50])) if subtotal > 1000 else Decimal('0')
            order = Order.objects.create(
                customer=rng.choice(customers) if customers and rng.random() < 0.35 else None,
                subtotal=subtotal, discount=discount, total=subtotal - discount, paid=subtotal - discount,
                payment_method=rng.choices(['cash', 'card', 'mobile'], weights=[6, 1, 3])[0], date=when,
            )
            ratio = order.total / subtotal
            remaining = order.total
            for i, (p, q) in enumerate(cart.items()):
                line = remaining if i == len(cart) - 1 else (p.price * q * ratio).quantize(TWO_PLACES)
                remaining -= line
                Sale.objects.create(order=order, product=p, quantity_sold=q, list_price=p.price,
                                    total_price=line, unit_cost=p.cost_price, date=when)
                log(p, -q, 'out', 'sale', when, order=order, unit_cost=p.cost_price)
            orders += 1
        day_start += timedelta(days=1)

    for p in products:
        p.save(update_fields=['quantity'])
    return orders
