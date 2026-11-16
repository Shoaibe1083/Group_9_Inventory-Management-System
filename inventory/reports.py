"""Numbers behind the Dashboard and Reports pages. Every function takes a
local date range [start, end] (inclusive) and works off Sale lines, so
profit always uses the buy price at the time of each sale."""
import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Category, Order, Product, Sale

MONEY = DecimalField(max_digits=14, decimal_places=2)
PROFIT_EXPR = ExpressionWrapper(F('total_price') - F('unit_cost') * F('quantity_sold'), output_field=MONEY)
ZERO = Decimal('0')

RANGES = [
    ('today', 'Today'),
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('90d', 'Last 90 days'),
    ('custom', 'Custom'),
]


def today():
    return timezone.localdate()


EARLIEST = date(2000, 1, 1)
LATEST = date(2099, 12, 31)
MAX_DAYS = 731  # a custom range covers at most two years


def parse_range(params, default='30d'):
    """Read ?range=…&start=YYYY-MM-DD&end=YYYY-MM-DD into (key, start, end)."""
    key = params.get('range', default)
    end = today()
    if key == 'custom':
        try:
            start = date.fromisoformat(params.get('start', ''))
            end = date.fromisoformat(params.get('end', ''))
        except ValueError:
            key = default
        else:
            if start > end:
                start, end = end, start
            # Dates like 0001-01-01 or 9999-12-31 used to crash the page
            # (date overflow); keep the range inside sensible limits.
            start = min(max(start, EARLIEST), LATEST)
            end = min(max(end, EARLIEST), LATEST)
            if (end - start).days >= MAX_DAYS:
                start = end - timedelta(days=MAX_DAYS - 1)
            return key, start, end
    days = {'today': 1, '7d': 7, '30d': 30, '90d': 90}.get(key)
    if days is None:
        key, days = default, 30
    return key, end - timedelta(days=days - 1), end


def bounds(start, end):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start, time.min), tz),
        timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz),
    )


def sales_in(start, end):
    lo, hi = bounds(start, end)
    return Sale.objects.filter(date__gte=lo, date__lt=hi)


def orders_in(start, end):
    lo, hi = bounds(start, end)
    return Order.objects.filter(date__gte=lo, date__lt=hi)


def summary(start, end):
    totals = sales_in(start, end).aggregate(
        revenue=Sum('total_price'), profit=Sum(PROFIT_EXPR), units=Sum('quantity_sold'),
    )
    revenue = totals['revenue'] or ZERO
    profit = totals['profit'] or ZERO
    orders = orders_in(start, end).count()
    return {
        'revenue': revenue,
        'profit': profit,
        'units': totals['units'] or 0,
        'orders': orders,
        'margin': (profit / revenue * 100) if revenue else ZERO,
        'basket': (revenue / orders) if orders else ZERO,
    }


def previous_period(start, end):
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def change(current, previous):
    """Percent change, or None when there is nothing to compare against."""
    if not previous:
        return None
    return float((current - previous) / abs(previous) * 100)


def daily(start, end):
    rows = {
        row['day']: row
        for row in sales_in(start, end)
        .annotate(day=TruncDate('date'))
        .values('day')
        .annotate(revenue=Sum('total_price'), profit=Sum(PROFIT_EXPR))
    }
    orders = {
        row['day']: row['n']
        for row in orders_in(start, end).annotate(day=TruncDate('date')).values('day').annotate(n=Count('id'))
    }
    series = []
    day = start
    while day <= end:
        row = rows.get(day, {})
        series.append({
            'day': day,
            'revenue': row.get('revenue') or ZERO,
            'profit': row.get('profit') or ZERO,
            'orders': orders.get(day, 0),
        })
        day += timedelta(days=1)
    return series


def top_products(start, end, limit=8):
    return list(
        sales_in(start, end)
        .values('product_id', 'product__name')
        .annotate(units=Sum('quantity_sold'), revenue=Sum('total_price'), profit=Sum(PROFIT_EXPR))
        .order_by('-units', '-revenue')[:limit]
    )


def by_category(start, end, fold_after=5):
    """Revenue share per category; anything past `fold_after` folds into Other."""
    rows = list(
        sales_in(start, end)
        .values('product__category__name')
        .annotate(revenue=Sum('total_price'), units=Sum('quantity_sold'))
        .order_by('-revenue')
    )
    total = sum((r['revenue'] for r in rows), ZERO)
    shown = [{'name': r['product__category__name'], 'revenue': r['revenue'], 'units': r['units']} for r in rows[:fold_after]]
    rest = rows[fold_after:]
    if rest:
        shown.append({
            'name': f'Other ({len(rest)})',
            'revenue': sum((r['revenue'] for r in rest), ZERO),
            'units': sum(r['units'] for r in rest),
        })
    for r in shown:
        r['share'] = float(r['revenue'] / total * 100) if total else 0.0
    return shown


def payment_split(start, end):
    labels = dict(Order.PAYMENT_CHOICES)
    return [
        {'method': labels.get(r['payment_method'], r['payment_method']), 'orders': r['n'], 'total': r['total']}
        for r in orders_in(start, end).values('payment_method').annotate(n=Count('id'), total=Sum('total')).order_by('-total')
    ]


def dead_stock(start, end, limit=50):
    """In-stock products that didn't sell once in the range, costliest first."""
    lo, hi = bounds(start, end)
    rows = (
        Product.objects.filter(quantity__gt=0)
        .annotate(sold=Count('sales', filter=Q(sales__date__gte=lo, sales__date__lt=hi)), last_sold=Max('sales__date'))
        .filter(sold=0)
        .select_related('category')
        .annotate(value=ExpressionWrapper(F('cost_price') * F('quantity'), output_field=MONEY))
        .order_by('-value')
    )
    return list(rows[:limit])


def reorder_suggestions(start, end, cover_days=14):
    """Products that will run out within `cover_days` at their current sales
    pace (or are already at the low-stock alert), with how many to order."""
    days = (end - start).days + 1
    lo, hi = bounds(start, end)
    products = (
        Product.objects.select_related('supplier', 'category')
        .annotate(sold=Sum('sales__quantity_sold', filter=Q(sales__date__gte=lo, sales__date__lt=hi)))
    )
    out = []
    for p in products:
        sold = p.sold or 0
        per_day = sold / days
        days_left = (p.quantity / per_day) if per_day else None
        low = p.quantity <= p.low_stock_threshold
        if not low and (days_left is None or days_left >= cover_days):
            continue
        target = math.ceil(per_day * cover_days) + p.low_stock_threshold
        if low:
            # A product sitting exactly on its alert level used to get target ==
            # quantity and drop out of the plan while the dashboard still showed
            # it as low. Order enough to lift it above the alert level.
            target = max(target, p.low_stock_threshold + 1)
        suggest = max(target - p.quantity, 0)
        if not suggest:
            continue
        out.append({
            'product': p,
            'per_day': per_day,
            'days_left': days_left,
            'suggest': suggest,
            'cost': p.cost_price * suggest,
            'urgent': p.quantity == 0 or (days_left is not None and days_left < 3),
        })
    out.sort(key=lambda r: (r['days_left'] if r['days_left'] is not None else 9999, -r['suggest']))
    return out


def inventory_health():
    qs = Product.objects.all()
    agg = qs.aggregate(
        units=Sum('quantity'),
        value=Sum(ExpressionWrapper(F('cost_price') * F('quantity'), output_field=MONEY)),
        retail=Sum(ExpressionWrapper(F('price') * F('quantity'), output_field=MONEY)),
    )
    return {
        'products': qs.count(),
        'units': agg['units'] or 0,
        'value': agg['value'] or ZERO,
        'retail': agg['retail'] or ZERO,
        'low': qs.filter(quantity__gt=0, quantity__lte=F('low_stock_threshold')).count(),
        'out': qs.filter(quantity=0).count(),
        'categories': Category.objects.count(),
    }


def telegram_text(store, start, end):
    s = summary(start, end)
    top = top_products(start, end, limit=5)
    low = Product.objects.filter(quantity__lte=F('low_stock_threshold')).order_by('quantity')[:8]
    span = start.strftime('%d %b %Y') if start == end else f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    lines = [
        f'📊 {store.shop_name} — {span}',
        '',
        f'Sales: ৳{s["revenue"]:,.2f}',
        f'Profit: ৳{s["profit"]:,.2f} ({s["margin"]:.1f}%)',
        f'Transactions: {s["orders"]}  ·  Units: {s["units"]}',
    ]
    if top:
        lines += ['', '🏆 Top products']
        lines += [f'{i}. {r["product__name"]} — {r["units"]} sold' for i, r in enumerate(top, 1)]
    if low:
        lines += ['', '⚠️ Low stock']
        lines += [f'• {p.name}: {p.quantity} left' for p in low]
    return '\n'.join(lines)
