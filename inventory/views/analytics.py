import json
import urllib.error
import urllib.parse
import urllib.request

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import reports
from ..models import StoreSettings
from .common import csv_response


@login_required
def report(request):
    key, start, end = reports.parse_range(request.GET)
    store = StoreSettings.load()
    current = reports.summary(start, end)
    prev_start, prev_end = reports.previous_period(start, end)
    previous = reports.summary(prev_start, prev_end)
    daily = reports.daily(start, end)
    top = reports.top_products(start, end, limit=8)
    categories = reports.by_category(start, end)
    days = (end - start).days + 1

    return render(request, 'inventory/report.html', {
        'ranges': reports.RANGES,
        'range_key': key,
        'start': start,
        'end': end,
        'days': days,
        'prev_start': prev_start,
        'prev_end': prev_end,
        'kpi': current,
        'delta': {
            'revenue': reports.change(current['revenue'], previous['revenue']),
            'profit': reports.change(current['profit'], previous['profit']),
            'margin': float(current['margin'] - previous['margin']) if previous['revenue'] else None,
            'orders': reports.change(current['orders'], previous['orders']),
            'basket': reports.change(current['basket'], previous['basket']),
        },
        'daily': daily,
        'top': top,
        'categories': categories,
        'payments': reports.payment_split(start, end),
        'dead': reports.dead_stock(start, end),
        'reorder': reports.reorder_suggestions(start, end, store.reorder_cover_days),
        'cover_days': store.reorder_cover_days,
        'chart': {
            'daily': {
                'labels': [d['day'].strftime('%d %b') for d in daily],
                'revenue': [float(d['revenue']) for d in daily],
                'profit': [float(d['profit']) for d in daily],
                'orders': [d['orders'] for d in daily],
            },
            'top': {
                'labels': [r['product__name'] for r in top],
                'units': [r['units'] for r in top],
                'revenue': [float(r['revenue']) for r in top],
            },
            'categories': {
                'labels': [c['name'] for c in categories],
                'revenue': [float(c['revenue']) for c in categories],
                'share': [round(c['share'], 1) for c in categories],
            },
        },
        'top_height': max(160, len(top) * 40 + 24),
        'qs': request.GET.urlencode(),
    })


@login_required
def report_export(request):
    key, start, end = reports.parse_range(request.GET)
    store = StoreSettings.load()
    response, writer = csv_response(f'report-{start:%Y%m%d}-{end:%Y%m%d}.csv')
    s = reports.summary(start, end)
    writer.writerow([f'{store.shop_name} — report {start:%d %b %Y} to {end:%d %b %Y}'])
    writer.writerow([])
    writer.writerow(['Summary'])
    writer.writerow(['Sales', s['revenue']])
    writer.writerow(['Profit', round(s['profit'], 2)])
    writer.writerow(['Margin %', round(s['margin'], 2)])
    writer.writerow(['Transactions', s['orders']])
    writer.writerow(['Units sold', s['units']])
    writer.writerow(['Average basket', round(s['basket'], 2)])

    writer.writerow([])
    writer.writerow(['Daily', 'Sales', 'Profit', 'Transactions'])
    for d in reports.daily(start, end):
        writer.writerow([d['day'].isoformat(), d['revenue'], round(d['profit'], 2), d['orders']])

    writer.writerow([])
    writer.writerow(['Top products', 'Units', 'Sales', 'Profit'])
    for r in reports.top_products(start, end, limit=50):
        writer.writerow([r['product__name'], r['units'], r['revenue'], round(r['profit'], 2)])

    writer.writerow([])
    writer.writerow(['Category', 'Units', 'Sales', 'Share %'])
    for c in reports.by_category(start, end, fold_after=100):
        writer.writerow([c['name'], c['units'], c['revenue'], round(c['share'], 1)])

    writer.writerow([])
    writer.writerow(['Dead stock (no sales in range)', 'SKU', 'In stock', 'Stock value', 'Last sold'])
    for p in reports.dead_stock(start, end, limit=500):
        writer.writerow([p.name, p.sku, p.quantity, p.value, p.last_sold.date().isoformat() if p.last_sold else 'never'])

    writer.writerow([])
    writer.writerow(['Reorder suggestion', 'SKU', 'In stock', 'Sold per day', 'Days left', 'Order qty', 'Est. cost', 'Supplier'])
    for r in reports.reorder_suggestions(start, end, store.reorder_cover_days):
        p = r['product']
        writer.writerow([
            p.name, p.sku, p.quantity, round(r['per_day'], 2),
            round(r['days_left'], 1) if r['days_left'] is not None else '', r['suggest'], r['cost'],
            p.supplier.name if p.supplier else '',
        ])
    return response


def send_telegram(store, text):
    """Returns None on success, or an error message."""
    if not store.telegram_ready:
        return 'Add your Telegram bot token and chat ID in Settings first.'
    url = f'https://api.telegram.org/bot{store.telegram_bot_token}/sendMessage'
    body = urllib.parse.urlencode({'chat_id': store.telegram_chat_id, 'text': text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=10) as resp:
            payload = json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get('description', '')
        except ValueError:
            detail = ''
        return f'Telegram refused the message ({error.code}{": " + detail if detail else ""}).'
    except (urllib.error.URLError, TimeoutError, OSError):
        return 'Could not reach Telegram — check the internet connection.'
    if not payload.get('ok'):
        return 'Telegram did not accept the message: ' + payload.get('description', 'unknown error')
    return None


@login_required
@require_POST
def report_telegram(request):
    key, start, end = reports.parse_range(request.POST)
    store = StoreSettings.load()
    error = send_telegram(store, reports.telegram_text(store, start, end))
    if error:
        messages.error(request, error)
    else:
        messages.success(request, 'Report sent to Telegram.')
    params = {'range': key}
    if key == 'custom':
        params.update(start=start.isoformat(), end=end.isoformat())
    return redirect(reverse('report') + '?' + '&'.join(f'{k}={v}' for k, v in params.items()))
