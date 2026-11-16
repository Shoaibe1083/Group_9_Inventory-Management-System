from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, ExpressionWrapper, F, Max, OuterRef, Q, Subquery, Sum
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import CategoryForm, CustomerForm, SupplierForm
from ..models import Category, Customer, StockIn, Supplier
from ..reports import MONEY
from .common import querystring


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@login_required
def supplier_list(request):
    # Purchases are summed in a subquery so joining products can't double-count them.
    purchases = (
        StockIn.objects.filter(supplier=OuterRef('pk'))
        .values('supplier')
        .annotate(total=Sum(ExpressionWrapper(F('unit_cost') * F('quantity'), output_field=MONEY)))
        .values('total')
    )
    suppliers = Supplier.objects.annotate(
        product_count=Count('products'),
        purchase_total=Subquery(purchases, output_field=MONEY),
    ).order_by('name')
    return render(request, 'inventory/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    form = SupplierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        supplier = form.save()
        messages.success(request, f'Supplier "{supplier.name}" has been added.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_form.html', {'form': form, 'title': 'Add Supplier'})


@login_required
def supplier_update(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    form = SupplierForm(request.POST or None, instance=supplier)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Supplier "{supplier.name}" has been updated.')
        return redirect('supplier_list')
    return render(request, 'inventory/supplier_form.html', {
        'form': form, 'title': 'Edit Supplier', 'supplier': supplier,
    })


@login_required
def supplier_delete(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        name = supplier.name
        supplier.delete()
        messages.success(request, f'Supplier "{name}" has been deleted.')
        return redirect('supplier_list')
    return render(request, 'inventory/confirm_delete.html', {
        'object_name': supplier.name,
        'kind': 'supplier',
        'note': f'{supplier.products.count()} product(s) will keep their data but lose this supplier link.',
        'cancel_url': 'supplier_list',
    })


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@login_required
def category_list(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        category = form.save()
        messages.success(request, f'Category "{category.name}" has been added.')
        return redirect('category_list')
    categories = Category.objects.annotate(
        product_count=Count('products'),
        stock_units=Sum('products__quantity'),
        low_count=Count('products', filter=Q(products__quantity__lte=F('products__low_stock_threshold'))),
    ).order_by('name')
    return render(request, 'inventory/category_list.html', {'form': form, 'categories': categories})


@login_required
def category_update(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Category "{category.name}" has been updated.')
        return redirect('category_list')
    return render(request, 'inventory/category_form.html', {'form': form, 'category': category})


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    count = category.products.count()
    if count:
        messages.error(
            request,
            f'"{category.name}" still has {count} product(s). Move or delete them before deleting the category.',
        )
        return redirect('category_list')
    if request.method == 'POST':
        name = category.name
        category.delete()
        messages.success(request, f'Category "{name}" has been deleted.')
        return redirect('category_list')
    return render(request, 'inventory/confirm_delete.html', {
        'object_name': category.name,
        'kind': 'category',
        'note': 'This category has no products, so nothing else will change.',
        'cancel_url': 'category_list',
    })


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@login_required
def customer_list(request):
    query = request.GET.get('q', '').strip()
    customers = Customer.objects.annotate(
        orders_count=Count('orders'), spent=Sum('orders__total'), last_visit=Max('orders__date'),
    )
    if query:
        customers = customers.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    sort = request.GET.get('sort', 'spent')
    if sort not in ('spent', 'recent', 'name'):
        sort = 'spent'
    customers = customers.order_by(*{
        'spent': [F('spent').desc(nulls_last=True), 'name'],
        'recent': [F('last_visit').desc(nulls_last=True), 'name'],
        'name': ['name', 'phone'],
    }[sort])
    return render(request, 'inventory/customer_list.html', {
        'page_obj': Paginator(customers, 20).get_page(request.GET.get('page')),
        'query': query,
        'sort': sort,
        'total': Customer.objects.count(),
        'page_qs': querystring(request, page=None),
    })


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    orders = customer.orders.annotate(lines=Count('items')).order_by('-date', '-pk')
    stats = orders.aggregate(spent=Sum('total'), last=Max('date'))
    return render(request, 'inventory/customer_detail.html', {
        'customer': customer,
        'orders': orders[:50],
        'stats': {**stats, 'count': orders.count()},
    })


@login_required
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        customer = form.save()
        messages.success(request, f'Customer "{customer}" has been added.')
        return redirect('customer_list')
    return render(request, 'inventory/customer_form.html', {'form': form, 'title': 'Add Customer'})


@login_required
def customer_update(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Customer "{customer}" has been updated.')
        return redirect('customer_detail', pk=customer.pk)
    return render(request, 'inventory/customer_form.html', {'form': form, 'title': 'Edit Customer', 'customer': customer})


@login_required
def customer_delete(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        name = str(customer)
        customer.delete()
        messages.success(request, f'Customer "{name}" has been deleted.')
        return redirect('customer_list')
    return render(request, 'inventory/confirm_delete.html', {
        'object_name': str(customer),
        'kind': 'customer',
        'note': f'Their {customer.orders.count()} receipt(s) stay in sales history without a customer name.',
        'cancel_url': 'customer_list',
    })
