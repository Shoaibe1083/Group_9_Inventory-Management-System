from django.contrib import admin

from .models import Category, Customer, Order, Product, Sale, StockIn, StockMovement, StoreSettings, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'address']
    search_fields = ['name', 'phone']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'created_at']
    search_fields = ['name', 'phone']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'barcode', 'category', 'supplier', 'cost_price', 'price', 'quantity', 'low_stock_threshold']
    list_filter = ['category', 'supplier']
    search_fields = ['name', 'sku', 'barcode']


@admin.register(StockIn)
class StockInAdmin(admin.ModelAdmin):
    list_display = ['product', 'supplier', 'quantity', 'unit_cost', 'date']
    list_filter = ['supplier', 'date']


class SaleInline(admin.TabularInline):
    model = Sale
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['pk', 'date', 'customer', 'payment_method', 'total', 'user']
    list_filter = ['payment_method', 'date']
    inlines = [SaleInline]


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['product', 'order', 'quantity_sold', 'total_price', 'unit_cost', 'date']
    list_filter = ['date']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['date', 'product', 'kind', 'reason', 'quantity', 'stock_after', 'user']
    list_filter = ['kind', 'reason', 'date']
    search_fields = ['product__name', 'note']


admin.site.register(StoreSettings)
