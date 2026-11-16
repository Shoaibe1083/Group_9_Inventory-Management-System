"""Fill in data the new POS / ledger screens rely on, for databases created
before them: SKU + barcode per product, one Order per old Sale, and a
StockMovement row for every past stock-in and sale."""
from django.db import migrations


def ean13(body12):
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


def forwards(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    Sale = apps.get_model('inventory', 'Sale')
    StockIn = apps.get_model('inventory', 'StockIn')
    Order = apps.get_model('inventory', 'Order')
    StockMovement = apps.get_model('inventory', 'StockMovement')

    for product in Product.objects.all():
        changed = []
        if not product.sku:
            product.sku = f'SKU-{product.pk:04d}'
            changed.append('sku')
        if not product.barcode:
            product.barcode = ean13(f'200{product.pk:09d}')
            changed.append('barcode')
        if changed:
            product.save(update_fields=changed)

    for sale in Sale.objects.filter(order__isnull=True).order_by('date'):
        order = Order.objects.create(
            subtotal=sale.total_price, total=sale.total_price, paid=sale.total_price, date=sale.date,
        )
        sale.order = order
        sale.save(update_fields=['order'])

    if StockMovement.objects.exists():
        return
    # Replay each product's history oldest-first. The opening balance is what
    # was on hand before the first record; older data didn't always keep the
    # quantity in step with its records, so a final stock-count row
    # reconciles the ledger with today's real quantity.
    for product in Product.objects.all():
        events = [
            (s.date, s.quantity, 'in', 'purchase', s.unit_cost, s.supplier_id, None)
            for s in StockIn.objects.filter(product=product)
        ] + [
            (s.date, -s.quantity_sold, 'out', 'sale', s.unit_cost, None, s.order_id)
            for s in Sale.objects.filter(product=product)
        ]
        events.sort(key=lambda e: e[0])
        net = sum(e[1] for e in events)
        running, lowest = 0, 0
        for event in events:
            running += event[1]
            lowest = min(lowest, running)
        opening = max(product.quantity - net, -lowest)

        rows = []
        balance = opening
        if opening:
            first = events[0][0] if events else product.created_at
            rows.append(StockMovement(
                product=product, kind='in', reason='opening', quantity=opening, stock_after=opening,
                unit_cost=product.cost_price, date=min(first, product.created_at), note='Opening stock',
            ))
        for date, qty, kind, reason, cost, supplier_id, order_id in events:
            balance += qty
            rows.append(StockMovement(
                product=product, kind=kind, reason=reason, quantity=qty, stock_after=balance,
                unit_cost=cost, supplier_id=supplier_id, order_id=order_id, date=date,
            ))
        if balance != product.quantity:
            rows.append(StockMovement(
                product=product, kind='adjust', reason='count', quantity=product.quantity - balance,
                stock_after=product.quantity, unit_cost=product.cost_price,
                date=events[-1][0], note='Reconciled when the stock ledger was introduced',
            ))
        StockMovement.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_pos_ledger_settings'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
