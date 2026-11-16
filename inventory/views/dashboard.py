from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.shortcuts import render
from django.utils import timezone

from .. import reports
from ..models import Order, Product


@login_required
def dashboard(request):
    today = reports.today()
    yesterday = today - timedelta(days=1)
    now_today = reports.summary(today, today)
    now_yesterday = reports.summary(yesterday, yesterday)
    month_start = today.replace(day=1)
    month = reports.summary(month_start, today)

    trend = reports.daily(today - timedelta(days=13), today)
    hour = timezone.localtime().hour
    greeting = 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening'

    return render(request, 'inventory/dashboard.html', {
        'greeting': greeting,
        'today': today,
        'kpi': now_today,
        'delta': {
            'revenue': reports.change(now_today['revenue'], now_yesterday['revenue']),
            'profit': reports.change(now_today['profit'], now_yesterday['profit']),
            'orders': reports.change(now_today['orders'], now_yesterday['orders']),
        },
        'month': month,
        'health': reports.inventory_health(),
        'low_stock': Product.objects.filter(quantity__lte=F('low_stock_threshold')).select_related('supplier').order_by('quantity', 'name')[:6],
        'recent_orders': Order.objects.select_related('customer').annotate(lines=Count('items')).order_by('-date')[:7],
        'top_products': reports.top_products(today - timedelta(days=29), today, limit=5),
        'chart': {
            'labels': [d['day'].strftime('%d %b') for d in trend],
            'revenue': [float(d['revenue']) for d in trend],
            'profit': [float(d['profit']) for d in trend],
        },
    })
