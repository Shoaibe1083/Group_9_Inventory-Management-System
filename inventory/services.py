"""Every change to stock goes through here, so product quantities and the
StockMovement ledger can never drift apart. Callers wrap these in
transaction.atomic()."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import Customer, Order, Product, Sale, StockIn, StockMovement, Supplier

TWO_PLACES = Decimal('0.01')
MAX_QUANTITY = 1_000_000  # largest quantity one line may carry


class StockError(Exception):
    """A request that would break a stock rule; the message is shown to the user."""


def ean13(body12):
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


def next_codes(product):
    """Default SKU and in-store EAN-13 barcode for a saved product."""
    return f'SKU-{product.pk:04d}', ean13(f'200{product.pk:09d}')


def find_by_code(code):
    code = (code or '').strip()
    if not code:
        return None
    return (
        Product.objects.select_related('category')
        .filter(barcode=code).first()
        or Product.objects.select_related('category').filter(sku__iexact=code).first()
    )


def to_decimal(value, default='0'):
    try:
        amount = Decimal(str(value if value not in (None, '') else default))
        if not amount.is_finite():  # "NaN" and "Infinity" are not amounts
            raise InvalidOperation
        return amount.quantize(TWO_PLACES)
    except (InvalidOperation, ValueError):
        raise StockError(f'"{value}" is not a valid amount.')


def to_int(value):
    # True/False and 1.5 used to slip through as 1; only whole numbers count.
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise StockError(f'"{value}" is not a valid quantity.')
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise StockError(f'"{value}" is not a valid quantity.')
    if abs(number) > MAX_QUANTITY:
        raise StockError(f'{number} is too large; the limit is {MAX_QUANTITY:,}.')
    return number


def _rows(lines):
    """The request's list of lines; anything else is rejected, not crashed on."""
    if not isinstance(lines, (list, tuple)) or not all(isinstance(line, dict) for line in lines):
        raise StockError('The request is not valid. Refresh the page and try again.')
    return lines


def move(product, quantity, kind, reason, user=None, **extra):
    """Apply a signed quantity change to a locked product and log it."""
    new_qty = product.quantity + quantity
    if new_qty < 0:
        raise StockError(f'Only {product.quantity} of "{product.name}" in stock.')
    product.quantity = new_qty
    product.save(update_fields=['quantity'])
    return StockMovement.objects.create(
        product=product, kind=kind, reason=reason, quantity=quantity,
        stock_after=new_qty, user=user, **extra,
    )


def _lock(ids):
    products = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    missing = set(ids) - set(products)
    if missing:
        raise StockError('A product in the list no longer exists. Refresh the page and try again.')
    return products


def _merge_lines(lines, field):
    """[{id, <field>}, …] -> {product_id: summed value}, rejecting junk."""
    merged = {}
    for line in _rows(lines):
        pk = to_int(line.get('id'))
        merged[pk] = merged.get(pk, 0) + to_int(line.get(field))
    return merged


def get_or_create_customer(data):
    data = data or {}
    if not isinstance(data, dict):
        raise StockError('The customer details are not valid.')
    if data.get('id'):
        return Customer.objects.filter(pk=to_int(data['id'])).first()
    name = (data.get('name') or '').strip()[:150]
    phone = (data.get('phone') or '').strip()[:20]
    if not name and not phone:
        return None
    if phone:
        customer = Customer.objects.filter(phone=phone).first()
        if customer:
            if name and not customer.name:
                customer.name = name
                customer.save(update_fields=['name'])
            return customer
    return Customer.objects.create(name=name, phone=phone)


@transaction.atomic
def checkout(items, user=None, customer=None, discount=0, paid=None, payment_method='cash', note=''):
    """Create an Order with one Sale per line and deduct stock."""
    cart = _merge_lines(items, 'qty')
    if not cart:
        raise StockError('The cart is empty.')
    if any(q < 1 for q in cart.values()):
        raise StockError('Every quantity must be at least 1.')
    if payment_method not in dict(Order.PAYMENT_CHOICES):
        payment_method = 'cash'

    products = _lock(list(cart))
    short = [p.name for pk, p in products.items() if cart[pk] > p.quantity]
    if short:
        raise StockError('Not enough stock for: ' + ', '.join(short) + '.')

    subtotal = sum((products[pk].price * qty for pk, qty in cart.items()), Decimal('0'))
    discount = min(max(to_decimal(discount), Decimal('0')), subtotal)
    total = subtotal - discount
    paid = total if paid in (None, '') else to_decimal(paid)
    if paid < total:
        raise StockError(f'Amount paid (৳{paid}) is less than the total (৳{total}).')

    now = timezone.now()
    order = Order.objects.create(
        customer=get_or_create_customer(customer), subtotal=subtotal, discount=discount,
        total=total, paid=paid, payment_method=payment_method, note=note[:255], user=user, date=now,
    )
    # Spread the discount over the lines by value so per-line profit stays
    # honest; the last line absorbs rounding so lines add up to the total.
    ratio = (total / subtotal) if subtotal else Decimal('1')
    remaining = total
    for index, (pk, qty) in enumerate(cart.items()):
        product = products[pk]
        is_last = index == len(cart) - 1
        line_total = remaining if is_last else (product.price * qty * ratio).quantize(TWO_PLACES)
        remaining -= line_total
        Sale.objects.create(
            order=order, product=product, quantity_sold=qty, list_price=product.price,
            total_price=line_total, unit_cost=product.cost_price, date=now,
        )
        move(product, -qty, 'out', 'sale', user, order=order, unit_cost=product.cost_price, date=now)
    return order


@transaction.atomic
def receive(lines, user=None, supplier_id=None, note=''):
    """Stock In: lines are [{id, qty, cost}]. Updates buy price to the latest cost."""
    supplier = Supplier.objects.filter(pk=supplier_id).first() if supplier_id else None
    parsed = {}
    for line in _rows(lines):
        pk, qty = to_int(line.get('id')), to_int(line.get('qty'))
        if qty < 1:
            raise StockError('Quantity received must be at least 1.')
        prev_qty, _ = parsed.get(pk, (0, None))
        parsed[pk] = (prev_qty + qty, line.get('cost'))
    if not parsed:
        raise StockError('Add at least one product.')

    products = _lock(list(parsed))
    now = timezone.now()
    units = 0
    for pk, (qty, cost) in parsed.items():
        product = products[pk]
        unit_cost = to_decimal(cost, product.cost_price)
        if unit_cost < 0:
            raise StockError('Cost cannot be negative.')
        StockIn.objects.create(product=product, supplier=supplier or product.supplier, quantity=qty, unit_cost=unit_cost)
        move(product, qty, 'in', 'purchase', user, unit_cost=unit_cost,
             supplier=supplier or product.supplier, note=note[:255], date=now)
        updates = ['cost_price']
        product.cost_price = unit_cost
        if supplier and not product.supplier_id:
            product.supplier = supplier
            updates.append('supplier')
        product.save(update_fields=updates)
        units += qty
    return len(parsed), units


@transaction.atomic
def adjust(lines, user=None, reason='count', note=''):
    """Adjustment. For a stock count lines are [{id, counted}] and the change is
    worked out against the locked quantity; otherwise lines are [{id, delta}]."""
    if reason not in StockMovement.ADJUST_REASONS:
        raise StockError('Pick a reason for the adjustment.')
    if reason == 'count':
        counted = {to_int(line.get('id')): to_int(line.get('counted')) for line in _rows(lines)}
        if any(c < 0 for c in counted.values()):
            raise StockError('A counted quantity cannot be negative.')
        products = _lock(list(counted))
        changes = {pk: c - products[pk].quantity for pk, c in counted.items()}
    else:
        changes = _merge_lines(lines, 'delta')
        products = _lock(list(changes))
    changes = {pk: d for pk, d in changes.items() if d}
    if not changes:
        raise StockError('Nothing to adjust — every line matches the current stock.')

    now = timezone.now()
    for pk, delta in changes.items():
        product = products[pk]
        move(product, delta, 'adjust', reason, user, unit_cost=product.cost_price, note=note[:255], date=now)
    return len(changes)
