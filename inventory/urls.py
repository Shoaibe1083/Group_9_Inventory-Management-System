from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('pos/', views.pos, name='pos'),
    path('pos/checkout/', views.pos_checkout, name='pos_checkout'),

    path('stock/', views.stock, name='stock'),
    path('stock/receive/', views.stock_receive, name='stock_receive'),
    path('stock/adjust/', views.stock_adjust, name='stock_adjust'),
    path('stock/history/export/', views.stock_history_export, name='stock_history_export'),

    path('alerts/', views.alert_list, name='alert_list'),
    path('alerts/export/', views.alert_export, name='alert_export'),

    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/export/', views.products_export, name='products_export'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<int:pk>/stock-in/', views.stock_in, name='stock_in'),
    path('products/<int:pk>/stock-out/', views.stock_out, name='stock_out'),

    path('sales/', views.order_list, name='order_list'),
    path('sales/export/', views.sales_export, name='sales_export'),
    path('sales/receipt/<int:pk>/', views.order_receipt, name='order_receipt'),
    path('sales/<int:pk>/receipt/', views.sale_receipt, name='sale_receipt'),

    path('reports/', views.report, name='report'),
    path('reports/export/', views.report_export, name='report_export'),
    path('reports/telegram/', views.report_telegram, name='report_telegram'),

    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),

    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_update, name='supplier_update'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),

    path('categories/', views.category_list, name='category_list'),
    path('categories/<int:pk>/edit/', views.category_update, name='category_update'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    path('settings/', views.settings_page, name='settings'),
    path('settings/users/add/', views.settings_user_create, name='settings_user_create'),
    path('settings/users/<int:pk>/edit/', views.settings_user_edit, name='settings_user_edit'),
    path('settings/users/<int:pk>/delete/', views.settings_user_delete, name='settings_user_delete'),
    path('settings/telegram/test/', views.settings_telegram_test, name='settings_telegram_test'),

    path('api/products/', views.api_product_search, name='api_product_search'),
    path('api/products/lookup/', views.api_product_lookup, name='api_product_lookup'),
    path('api/customers/', views.api_customer_search, name='api_customer_search'),
]
