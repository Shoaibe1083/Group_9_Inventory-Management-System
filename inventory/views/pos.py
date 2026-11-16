from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import reports, services
from ..models import Customer, Order, Product, Sale
from .common import csv_response, json_body, json_error, querystring

PERIODS = [
    ('today', 'Today'),
    ('7d', 'Last 7 days'),
    ('30d', 'Last 30 days'),
    ('all', 'All time'),
]


@login_required
def pos(request):
    preload = None
    if request.GET.get('add', '').isdigit():
        product = Product.objects.select_related('category').filter(pk=request.GET['add']).first()
        preload = product.as_json() if product else None
    return render(request, 'inventory/pos.html', {
        'preload': preload,
        'payment_choices': Order.PAYMENT_CHOICES,
        'quick_products': [
            p.as_json() for p in Product.objects.select_related('category').filter(quantity__gt=0)
            .annotate(sold=Sum('sales__quantity_sold')).order_by('-sold', 'name')[:8]
        ],
    })


@login_required
@require_POST
def pos_checkout(request):
    data = json_body(request)
    try:
        order = services.checkout(
            data.get('items') or [],
            user=request.user,
            customer=data.get('customer'),
            discount=data.get('discount') or 0,
            paid=data.get('paid'),
            payment_method=data.get('payment') or 'cash',
            note=str(data.get('note') or ''),
        )
    except services.StockError as error:
        return json_error(str(error))
    return JsonResponse({
        'ok': True,
        'order': order.pk,
        'total': str(order.total),
        'change': str(order.change),
        'receipt_url': reverse('order_receipt', args=[order.pk]),
    })


@login_required
def api_customer_search(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    customers = (
        Customer.objects.filter(Q(name__icontains=query) | Q(phone__icontains=query))
        .annotate(orders_count=Count('orders'), spent=Sum('orders__total'))
        .order_by('name')[:8]
    )
    return JsonResponse({'results': [
        {'id': c.pk, 'name': c.name, 'phone': c.phone, 'orders': c.orders_count, 'spent': str(c.spent or 0)}
        for c in customers
    ]})


# ---------------------------------------------------------------------------
# Sales (transactions)
# ---------------------------------------------------------------------------

def _filtered_orders(request):
    period = request.GET.get('period', '30d')
    if period not in dict(PERIODS):
        period = '30d'
    query = request.GET.get('q', '').strip()
    payment = request.GET.get('payment', '')
    orders = Order.objects.select_related('customer', 'user')
    if period != 'all':
        _, start, end = reports.parse_range({'range': period})
        lo, hi = reports.bounds(start, end)
        orders = orders.filter(date__gte=lo, date__lt=hi)
    if payment in dict(Order.PAYMENT_CHOICES):
        orders = orders.filter(payment_method=payment)
    if query:
        filters = Q(customer__name__icontains=query) | Q(customer__phone__icontains=query) | Q(items__product__name__icontains=query)
        if query.lstrip('#').isdigit():
            filters |= Q(pk=int(query.lstrip('#')))
        orders = orders.filter(pk__in=Order.objects.filter(filters).values('pk'))
    return orders, period, query, payment


@login_required
def order_list(request):
    orders, period, query, payment = _filtered_orders(request)
    lines = Sale.objects.filter(order__in=orders.values('pk'))
    totals = lines.aggregate(revenue=Sum('total_price'), profit=Sum(reports.PROFIT_EXPR), units=Sum('quantity_sold'))
    count = orders.count()
    page_obj = Paginator(
        orders.annotate(lines=Count('items', distinct=True), units=Sum('items__quantity_sold')).order_by('-date', '-pk'),
        20,
    ).get_page(request.GET.get('page'))
    return render(request, 'inventory/order_list.html', {
        'page_obj': page_obj,
        'periods': PERIODS,
        'period': period,
        'query': query,
        'payment': payment,
        'payment_choices': Order.PAYMENT_CHOICES,
        'totals': {
            'revenue': totals['revenue'] or 0,
            'profit': totals['profit'] or 0,
            'units': totals['units'] or 0,
            'count': count,
            'basket': (totals['revenue'] or 0) / count if count else 0,
        },
        'page_qs': querystring(request, page=None),
    })


@login_required
def sales_export(request):
    orders, period, _, _ = _filtered_orders(request)
    response, writer = csv_response(f'sales-{period}-{timezone.localdate():%Y%m%d}.csv')
    writer.writerow(['Receipt', 'Date', 'Customer', 'Payment', 'Product', 'SKU', 'Quantity', 'Unit Price', 'Line Total', 'Profit'])
    lines = (
        Sale.objects.filter(order__in=orders.values('pk'))
        .select_related('order__customer', 'product').order_by('-date', 'order_id')
    )
    for s in lines:
        o = s.order
        writer.writerow([
            o.pk, timezone.localtime(s.date).strftime('%d %b %Y %I:%M %p'),
            str(o.customer) if o.customer else '', o.get_payment_method_display(),
            s.product.name, s.product.sku, s.quantity_sold, round(s.unit_price, 2), s.total_price, round(s.profit, 2),
        ])
    return response


@login_required
def order_receipt(request, pk):
    order = get_object_or_404(Order.objects.select_related('customer', 'user'), pk=pk)
    items = order.items.select_related('product')
    return render(request, 'inventory/receipt.html', {
        'order': order,
        'items': items,
        'units': sum(i.quantity_sold for i in items),
        'just_sold': request.GET.get('new') == '1',
    })


@login_required
def sale_receipt(request, pk):
    """Old per-line receipt links now open the whole order."""
    sale = get_object_or_404(Sale, pk=pk)
    if not sale.order_id:
        messages.error(request, 'That sale has no receipt.')
        return redirect('order_list')
    return redirect('order_receipt', pk=sale.order_id)
