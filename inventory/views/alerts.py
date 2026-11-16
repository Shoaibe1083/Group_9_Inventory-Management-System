from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import F, Max, Q
from django.shortcuts import render
from django.utils import timezone

from .. import reports
from ..models import Category, Product, StoreSettings
from .common import csv_response

TABS = [
    ('', 'All alerts'),
    ('out', 'Out of stock'),
    ('low', 'Low stock'),
]


def _alert_products(request):
    """Products at or below their alert level, emptiest first, each with a
    suggested order quantity from the last 30 days of sales."""
    status = request.GET.get('status', '')
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')

    alerts = Product.objects.filter(quantity__lte=F('low_stock_threshold'))
    counts = {
        '': alerts.count(),
        'out': alerts.filter(quantity=0).count(),
        'low': alerts.filter(quantity__gt=0).count(),
    }
    products = alerts.select_related('category', 'supplier').annotate(last_sold=Max('sales__date'))
    if status == 'out':
        products = products.filter(quantity=0)
    elif status == 'low':
        products = products.filter(quantity__gt=0)
    else:
        status = ''
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode=query))
    if category.isdigit():
        products = products.filter(category_id=category)
    products = list(products.order_by('quantity', 'name'))

    today = reports.today()
    cover_days = StoreSettings.load().reorder_cover_days
    suggestions = {
        r['product'].pk: r
        for r in reports.reorder_suggestions(today - timedelta(days=29), today, cover_days)
    }
    for p in products:
        suggestion = suggestions.get(p.pk)
        # Nothing sold lately: just refill to twice the alert level.
        p.suggest = suggestion['suggest'] if suggestion else max(p.low_stock_threshold * 2 - p.quantity, 1)
        p.per_day = suggestion['per_day'] if suggestion else 0
        p.days_left = suggestion['days_left'] if suggestion else None
        p.order_cost = p.cost_price * p.suggest
        p.fill = min(100, round(p.quantity / p.low_stock_threshold * 100)) if p.low_stock_threshold else 0
    return products, counts, {'status': status, 'q': query, 'category': category}, cover_days


@login_required
def alert_list(request):
    products, counts, filters, cover_days = _alert_products(request)
    return render(request, 'inventory/alert_list.html', {
        'products': products,
        'tabs': [(key, label, counts[key]) for key, label in TABS],
        'counts': counts,
        'filters': filters,
        'categories': Category.objects.all(),
        'cover_days': cover_days,
        'order_cost': sum(p.order_cost for p in products),
        'order_units': sum(p.suggest for p in products),
        'qs': request.GET.urlencode(),
    })


@login_required
def alert_export(request):
    products, _, _, _ = _alert_products(request)
    response, writer = csv_response(f'stock-alerts-{timezone.localdate():%Y%m%d}.csv')
    writer.writerow(['Product', 'SKU', 'Category', 'Supplier', 'Supplier Phone', 'In Stock', 'Alert At',
                     'Status', 'Sold / Day', 'Suggested Order', 'Buy Price', 'Est. Cost'])
    for p in products:
        writer.writerow([
            p.name, p.sku, p.category.name, p.supplier.name if p.supplier else '',
            p.supplier.phone if p.supplier else '', p.quantity, p.low_stock_threshold,
            'Out of stock' if p.quantity == 0 else 'Low stock', round(p.per_day, 2),
            p.suggest, p.cost_price, p.order_cost,
        ])
    return response
