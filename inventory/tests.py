import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from .models import Category, Customer, Order, Product, StockMovement, StoreSettings, Supplier
from .services import StockError, adjust, checkout, receive

User = get_user_model()


def make_product(name='Rice', qty=10, price='100', cost='80', **extra):
    category, _ = Category.objects.get_or_create(name='Grocery')
    return Product.objects.create(
        name=name, category=category, price=Decimal(price), cost_price=Decimal(cost), quantity=qty, **extra,
    )


class ServiceTests(TestCase):
    def setUp(self):
        self.rice = make_product('Rice', qty=10, price='100', cost='80', barcode='111')
        self.oil = make_product('Oil', qty=5, price='50', cost='40', sku='OIL-1')

    def test_checkout_deducts_stock_and_logs_ledger(self):
        order = checkout([{'id': self.rice.pk, 'qty': 3}, {'id': self.oil.pk, 'qty': 1}],
                         customer={'phone': '01711', 'name': 'Nusrat'})
        self.rice.refresh_from_db()
        self.oil.refresh_from_db()
        self.assertEqual((self.rice.quantity, self.oil.quantity), (7, 4))
        self.assertEqual(order.total, Decimal('350.00'))
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.customer.phone, '01711')
        self.assertEqual(StockMovement.objects.filter(order=order).aggregate(t=Sum('quantity'))['t'], -4)

    def test_discount_is_spread_and_lines_add_up(self):
        order = checkout([{'id': self.rice.pk, 'qty': 1}, {'id': self.oil.pk, 'qty': 1}], discount='10')
        self.assertEqual(order.total, Decimal('140.00'))
        self.assertEqual(order.items.aggregate(t=Sum('total_price'))['t'], order.total)
        self.assertEqual(order.items.get(product=self.rice).list_price, Decimal('100'))

    def test_checkout_rejects_overselling_and_changes_nothing(self):
        with self.assertRaises(StockError):
            checkout([{'id': self.rice.pk, 'qty': 1}, {'id': self.oil.pk, 'qty': 99}])
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, 10)
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_underpayment(self):
        with self.assertRaises(StockError):
            checkout([{'id': self.rice.pk, 'qty': 1}], paid='50')

    def test_existing_customer_is_reused_by_phone(self):
        Customer.objects.create(name='Old', phone='0199')
        checkout([{'id': self.rice.pk, 'qty': 1}], customer={'phone': '0199', 'name': ''})
        self.assertEqual(Customer.objects.count(), 1)

    def test_receive_updates_qty_cost_and_supplier(self):
        supplier = Supplier.objects.create(name='Karim')
        receive([{'id': self.rice.pk, 'qty': 5, 'cost': '85'}], supplier_id=supplier.pk)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, 15)
        self.assertEqual(self.rice.cost_price, Decimal('85'))
        self.assertEqual(self.rice.supplier, supplier)
        m = self.rice.movements.get()
        self.assertEqual((m.kind, m.reason, m.quantity, m.stock_after), ('in', 'purchase', 5, 15))

    def test_stock_count_uses_counted_quantity_against_live_stock(self):
        adjust([{'id': self.rice.pk, 'counted': 7}], reason='count')
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, 7)
        self.assertEqual(self.rice.movements.get().quantity, -3)

    def test_adjust_cannot_go_negative(self):
        with self.assertRaises(StockError):
            adjust([{'id': self.oil.pk, 'delta': -6}], reason='damage')

    def test_adjust_rejects_unknown_reason(self):
        with self.assertRaises(StockError):
            adjust([{'id': self.oil.pk, 'delta': -1}], reason='sale')


class SeedTests(TestCase):
    def test_seed_builds_a_consistent_ledger(self):
        call_command('seed', stdout=open('/dev/null', 'w'))
        self.assertTrue(Order.objects.exists())
        for p in Product.objects.all():
            moves = p.movements.order_by('date', 'pk')
            self.assertEqual(moves.aggregate(t=Sum('quantity'))['t'], p.quantity, p.name)
            self.assertEqual(moves.last().stock_after, p.quantity, p.name)
            self.assertGreaterEqual(min(m.stock_after for m in moves), 0, p.name)
        for o in Order.objects.all()[:50]:
            self.assertEqual(o.items.aggregate(t=Sum('total_price'))['t'], o.total)


class ImportCatalogTests(TestCase):
    def test_import_on_top_of_existing_history_keeps_ledger_consistent(self):
        rice = make_product('Old Rice', qty=0)
        receive([{'id': rice.pk, 'qty': 20, 'cost': '80'}])
        checkout([{'id': rice.pk, 'qty': 3}])
        call_command('import_catalog', demo_sales=5, stdout=open('/dev/null', 'w'))
        self.assertGreaterEqual(Product.objects.count(), 100)
        # Running it again adds nothing new.
        before = Product.objects.count()
        call_command('import_catalog', stdout=open('/dev/null', 'w'))
        self.assertEqual(Product.objects.count(), before)
        for p in Product.objects.all():
            moves = list(p.movements.order_by('date', 'pk'))
            self.assertEqual(sum(m.quantity for m in moves), p.quantity, p.name)
            self.assertEqual(moves[-1].stock_after, p.quantity, p.name)
            self.assertTrue(all(m.stock_after >= 0 for m in moves), p.name)


class ViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        self.client.force_login(self.admin)
        call_command('seed', stdout=open('/dev/null', 'w'))
        self.product = Product.objects.filter(quantity__gt=2).first()

    def test_every_page_renders(self):
        order = Order.objects.first()
        customer = Customer.objects.first()
        supplier = Supplier.objects.first()
        category = Category.objects.first()
        urls = [
            reverse('dashboard'), reverse('pos'), reverse('pos') + f'?add={self.product.pk}',
            reverse('stock'), reverse('stock') + '?tab=adjust',
            reverse('stock') + '?tab=history&kind=out&start=2020-01-01&end=2099-01-01',
            reverse('product_list'), reverse('product_list') + '?status=low&q=a',
            reverse('alert_list'), reverse('alert_list') + '?status=out&q=a&category=1', reverse('alert_export'),
            reverse('product_detail', args=[self.product.pk]), reverse('product_create'),
            reverse('product_update', args=[self.product.pk]), reverse('product_delete', args=[self.product.pk]),
            reverse('stock_in', args=[self.product.pk]),
            reverse('order_list'), reverse('order_list') + '?period=all&q=1', reverse('order_receipt', args=[order.pk]),
            reverse('report'), reverse('report') + '?range=today', reverse('report') + '?range=7d',
            reverse('report') + '?range=custom&start=2026-01-01&end=2026-12-31',
            reverse('report') + '?range=custom&start=bad',
            reverse('customer_list'), reverse('customer_detail', args=[customer.pk]),
            reverse('customer_create'), reverse('customer_update', args=[customer.pk]),
            reverse('supplier_list'), reverse('supplier_create'), reverse('supplier_update', args=[supplier.pk]),
            reverse('category_list'), reverse('category_update', args=[category.pk]),
            reverse('settings'), reverse('settings') + '?tab=store', reverse('settings') + '?tab=users',
            reverse('settings') + '?tab=telegram', reverse('settings') + '?tab=appearance', reverse('settings_user_create'),
            reverse('settings_user_edit', args=[self.admin.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_csv_exports(self):
        for name in ['products_export', 'sales_export', 'report_export', 'stock_history_export']:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn('text/csv', response['Content-Type'])

    def test_pos_checkout_endpoint(self):
        before = self.product.quantity
        response = self.client.post(
            reverse('pos_checkout'),
            data=json.dumps({'items': [{'id': self.product.pk, 'qty': 2}], 'payment': 'cash', 'paid': '100000'}),
            content_type='application/json',
        )
        data = response.json()
        self.assertTrue(data['ok'], data)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, before - 2)
        self.assertEqual(self.client.get(data['receipt_url']).status_code, 200)

    def test_pos_checkout_error_is_json(self):
        response = self.client.post(reverse('pos_checkout'), data='{"items": []}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_lookup_by_barcode(self):
        response = self.client.get(reverse('api_product_lookup') + f'?code={self.product.barcode}')
        self.assertEqual(response.json()['product']['id'], self.product.pk)

    def test_stock_receive_and_adjust_endpoints(self):
        r = self.client.post(reverse('stock_receive'), content_type='application/json',
                             data=json.dumps({'lines': [{'id': self.product.pk, 'qty': 4, 'cost': '10'}]}))
        self.assertTrue(r.json()['ok'])
        r = self.client.post(reverse('stock_adjust'), content_type='application/json',
                             data=json.dumps({'reason': 'count', 'lines': [{'id': self.product.pk, 'counted': 1}]}))
        self.assertTrue(r.json()['ok'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 1)

    def test_new_product_gets_codes_and_opening_movement(self):
        response = self.client.post(reverse('product_create'), {
            'name': 'Tea', 'category': Category.objects.first().pk, 'cost_price': '10', 'price': '12',
            'quantity': '6', 'low_stock_threshold': '2', 'sku': '', 'barcode': '',
        })
        self.assertEqual(response.status_code, 302)
        tea = Product.objects.get(name='Tea')
        self.assertTrue(tea.sku and tea.barcode)
        self.assertEqual(tea.quantity, 6)
        self.assertEqual(tea.movements.get().reason, 'opening')

    def test_duplicate_barcode_rejected(self):
        response = self.client.post(reverse('product_create'), {
            'name': 'Dup', 'category': Category.objects.first().pk, 'cost_price': '1', 'price': '2',
            'quantity': '0', 'low_stock_threshold': '1', 'barcode': self.product.barcode,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name='Dup').exists())


class AccountTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')

    def test_login_with_email_or_username(self):
        for login in ['admin', 'ADMIN@example.com']:
            self.client.logout()
            response = self.client.post(reverse('login'), {'username': login, 'password': 'admin123'})
            self.assertEqual(response.status_code, 302, login)

    def test_change_own_email_and_password(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('settings'), {
            'action': 'account', 'username': 'boss', 'email': 'Boss@Shop.com', 'first_name': 'Hasan', 'last_name': '',
        })
        self.admin.refresh_from_db()
        self.assertEqual((self.admin.username, self.admin.email), ('boss', 'boss@shop.com'))

        response = self.client.post(reverse('settings'), {
            'action': 'password', 'old_password': 'admin123',
            'new_password1': 'Kh4t-Shop!2026', 'new_password2': 'Kh4t-Shop!2026',
        })
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('Kh4t-Shop!2026'))
        # Still signed in after the change.
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_wrong_current_password_is_rejected(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('settings'), {
            'action': 'password', 'old_password': 'nope', 'new_password1': 'Kh4t-Shop!2026', 'new_password2': 'Kh4t-Shop!2026',
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('admin123'))

    def test_admin_can_add_staff_who_cannot_open_admin_settings(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('settings_user_create'), {
            'username': 'cashier', 'email': 'cashier@shop.com', 'role': 'staff', 'is_active': 'on',
            'new_password1': 'Counter-2026!x', 'new_password2': 'Counter-2026!x',
        })
        self.assertEqual(response.status_code, 302)
        staff = User.objects.get(username='cashier')
        self.assertFalse(staff.is_superuser)

        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('settings_user_create')).status_code, 302)
        self.client.post(reverse('settings'), {'action': 'store', 'shop_name': 'Hacked', 'receipt_footer': 'x',
                                               'default_low_stock': 1, 'reorder_cover_days': 5})
        self.assertNotEqual(StoreSettings.load().shop_name, 'Hacked')

    def test_last_admin_cannot_be_demoted_or_deleted(self):
        other = User.objects.create_user('other', 'o@x.com', 'pw', is_staff=True)
        self.client.force_login(self.admin)
        # Can't delete yourself.
        self.client.post(reverse('settings_user_delete', args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        # Promote other, then demoting the original admin is fine…
        other.is_superuser = True
        other.save()
        self.client.force_login(other)
        self.client.post(reverse('settings_user_edit', args=[self.admin.pk]), {
            'username': 'admin', 'email': 'admin@example.com', 'role': 'staff', 'is_active': 'on',
        })
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_superuser)
        # …but other is now the only admin and can't be removed by anyone.
        self.client.force_login(other)
        self.client.post(reverse('settings_user_delete', args=[other.pk]))
        self.assertTrue(User.objects.filter(pk=other.pk).exists())

    def test_pages_require_login(self):
        self.assertEqual(self.client.get(reverse('pos')).status_code, 302)
        self.assertEqual(self.client.get(reverse('api_product_search')).status_code, 302)
