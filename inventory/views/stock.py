from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import reports, services
from ..models import StockMovement, Supplier
from .common import csv_response, json_body, json_error, querystring

TABS = ['in', 'adjust', 'history']


def _history(request):
    movements = StockMovement.objects.select_related('product', 'supplier', 'order', 'user')
    query = request.GET.get('q', '').strip()
    kind = request.GET.get('kind', '')
    reason = request.GET.get('reason', '')
    start, end = request.GET.get('start', ''), request.GET.get('end', '')
    if query:
        movements = movements.filter(
            Q(product__name__icontains=query) | Q(product__sku__icontains=query)
            | Q(product__barcode=query) | Q(note__icontains=query)
        )
    if kind in dict(StockMovement.KIND_CHOICES):
        movements = movements.filter(kind=kind)
    if reason in dict(StockMovement.REASON_CHOICES):
        movements = movements.filter(reason=reason)
    try:
        lo, _ = reports.bounds(date.fromisoformat(start), date.fromisoformat(start))
        movements = movements.filter(date__gte=lo)
    except ValueError:
        start = ''
    try:
        _, hi = reports.bounds(date.fromisoformat(end), date.fromisoformat(end))
        movements = movements.filter(date__lt=hi)
    except ValueError:
        end = ''
    return movements, {'q': query, 'kind': kind, 'reason': reason, 'start': start, 'end': end}


@login_required
def stock(request):
    tab = request.GET.get('tab', 'in')
    if tab not in TABS:
        tab = 'in'
    context = {
        'tab': tab,
        'suppliers': Supplier.objects.all(),
        'adjust_reasons': [(k, v) for k, v in StockMovement.REASON_CHOICES if k in StockMovement.ADJUST_REASONS],
    }
    if tab == 'history':
        movements, filters = _history(request)
        totals = movements.aggregate(
            added=Sum('quantity', filter=Q(quantity__gt=0)),
            removed=Sum('quantity', filter=Q(quantity__lt=0)),
        )
        context.update({
            'page_obj': Paginator(movements, 25).get_page(request.GET.get('page')),
            'filters': filters,
            'kinds': StockMovement.KIND_CHOICES,
            'reasons': StockMovement.REASON_CHOICES,
            'totals': {'added': totals['added'] or 0, 'removed': -(totals['removed'] or 0)},
            'page_qs': querystring(request, page=None),
        })
    return render(request, 'inventory/stock.html', context)


@login_required
@require_POST
def stock_receive(request):
    data = json_body(request)
    try:
        products, units = services.receive(
            data.get('lines') or [], user=request.user,
            supplier_id=data.get('supplier') or None, note=str(data.get('note') or ''),
        )
    except services.StockError as error:
        return json_error(str(error))
    messages.success(request, f'Received {units} units across {products} product{"s" if products != 1 else ""}.')
    return JsonResponse({'ok': True, 'redirect': reverse('stock') + '?tab=history'})


@login_required
@require_POST
def stock_adjust(request):
    data = json_body(request)
    try:
        count = services.adjust(
            data.get('lines') or [], user=request.user,
            reason=data.get('reason') or '', note=str(data.get('note') or ''),
        )
    except services.StockError as error:
        return json_error(str(error))
    messages.success(request, f'Adjusted stock for {count} product{"s" if count != 1 else ""}.')
    return JsonResponse({'ok': True, 'redirect': reverse('stock') + '?tab=history'})


@login_required
def stock_history_export(request):
    movements, _ = _history(request)
    response, writer = csv_response(f'stock-ledger-{timezone.localdate():%Y%m%d}.csv')
    writer.writerow(['Date', 'Product', 'SKU', 'Type', 'Reference', 'Change', 'Stock After', 'Unit Cost',
                     'Value', 'Supplier', 'Receipt', 'Note', 'By'])
    for m in movements[:20000]:
        writer.writerow([
            timezone.localtime(m.date).strftime('%d %b %Y %I:%M %p'), m.product.name, m.product.sku,
            m.get_kind_display(), m.get_reason_display(), m.quantity, m.stock_after, m.unit_cost, m.value,
            m.supplier.name if m.supplier else '', m.order_id or '', m.note, m.user.username if m.user else '',
        ])
    return response
