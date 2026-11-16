from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .. import services
from ..forms import ProductForm, StockInForm
from ..models import Category, Product
from ..reports import PROFIT_EXPR
from .common import csv_response, querystring

STATUSES = [
    ('', 'All'),
    ('low', 'Low stock'),
    ('out', 'Out of stock'),
]


def _search(products, query):
    return products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode=query))


@login_required
def product_list(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    category = request.GET.get('category', '')
    products = Product.objects.select_related('category', 'supplier')
    if query:
        products = _search(products, query)
    if status == 'low':
        products = products.filter(quantity__gt=0, quantity__lte=F('low_stock_threshold'))
    elif status == 'out':
        products = products.filter(quantity=0)
    if category.isdigit():
        products = products.filter(category_id=category)

    page_obj = Paginator(products, 12).get_page(request.GET.get('page'))
    all_products = Product.objects.all()
    counts = {
        '': all_products.count(),
        'low': all_products.filter(quantity__gt=0, quantity__lte=F('low_stock_threshold')).count(),
        'out': all_products.filter(quantity=0).count(),
    }
    return render(request, 'inventory/product_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'category': category,
        'categories': Category.objects.all(),
        'statuses': [(key, label, counts[key]) for key, label in STATUSES],
        'page_qs': querystring(request, page=None),
    })


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category', 'supplier'), pk=pk)
    totals = product.sales.aggregate(revenue=Sum('total_price'), profit=Sum(PROFIT_EXPR), units=Sum('quantity_sold'))
    return render(request, 'inventory/product_detail.html', {
        'product': product,
        'summary': totals,
        'movements': product.movements.select_related('supplier', 'order', 'user')[:40],
        'total_stocked_in': product.movements.filter(kind='in').aggregate(t=Sum('quantity'))['t'] or 0,
    })


@login_required
def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            opening = form.cleaned_data['quantity']
            product = form.save(commit=False)
            product.quantity = 0
            product.save()
            sku, barcode = services.next_codes(product)
            product.sku = product.sku or sku
            product.barcode = product.barcode or barcode
            product.save(update_fields=['sku', 'barcode'])
            if opening:
                services.move(product, opening, 'in', 'opening', request.user,
                              unit_cost=product.cost_price, note='Opening stock')
        messages.success(request, f'"{product.name}" has been added.')
        return redirect('product_detail', pk=product.pk)
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Add Product'})


@login_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        product = form.save(commit=False)
        if not product.sku or not product.barcode:
            sku, barcode = services.next_codes(product)
            product.sku = product.sku or sku
            product.barcode = product.barcode or barcode
        product.save()
        messages.success(request, f'"{product.name}" has been updated.')
        return redirect('product_detail', pk=product.pk)
    return render(request, 'inventory/product_form.html', {'form': form, 'title': 'Edit Product', 'product': product})


@login_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        name = product.name
        product.delete()
        messages.success(request, f'"{name}" has been deleted.')
        return redirect('product_list')
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


@login_required
def products_export(request):
    response, writer = csv_response('products.csv')
    writer.writerow(['Product', 'SKU', 'Barcode', 'Category', 'Supplier', 'Buy Price', 'Sell Price',
                     'Profit/Unit', 'In Stock', 'Stock Value', 'Status'])
    for p in Product.objects.select_related('category', 'supplier').order_by('name'):
        status = 'Out of stock' if p.quantity == 0 else 'Low stock' if p.is_low_stock else 'In stock'
        writer.writerow([
            p.name, p.sku, p.barcode, p.category.name, p.supplier.name if p.supplier else '',
            p.cost_price, p.price, p.profit_per_unit, p.quantity, p.stock_value, status,
        ])
    return response


@login_required
def stock_in(request, pk):
    """Quick stock-in for one product (from the product page)."""
    product = get_object_or_404(Product, pk=pk)
    form = StockInForm(request.POST or None, initial={'supplier': product.supplier_id, 'unit_cost': product.cost_price})
    if request.method == 'POST' and form.is_valid():
        supplier = form.cleaned_data['supplier']
        services.receive(
            [{'id': product.pk, 'qty': form.cleaned_data['quantity'], 'cost': form.cleaned_data['unit_cost']}],
            user=request.user, supplier_id=supplier.pk if supplier else None,
        )
        messages.success(request, f'Added {form.cleaned_data["quantity"]} units to "{product.name}".')
        return redirect('product_detail', pk=product.pk)
    return render(request, 'inventory/stock_form.html', {'form': form, 'product': product})


@login_required
def stock_out(request, pk):
    """Selling now happens in the POS — open it with this product in the cart."""
    get_object_or_404(Product, pk=pk)
    return redirect(f'{reverse("pos")}?add={pk}')


# ---------------------------------------------------------------------------
# JSON lookups used by the POS and Stock screens
# ---------------------------------------------------------------------------

@login_required
def api_product_search(request):
    query = request.GET.get('q', '').strip()
    products = Product.objects.select_related('category')
    if query:
        products = _search(products, query)
    supplier = request.GET.get('supplier', '')
    if supplier.isdigit():
        products = products.filter(supplier_id=supplier)
    if request.GET.get('in_stock'):
        products = products.filter(quantity__gt=0)
    products = products.order_by('name')[:20]
    return JsonResponse({'results': [p.as_json() for p in products]})


@login_required
def api_product_lookup(request):
    product = services.find_by_code(request.GET.get('code'))
    if not product:
        return JsonResponse({'ok': False, 'error': 'No product with that barcode or SKU.'}, status=404)
    return JsonResponse({'ok': True, 'product': product.as_json()})
