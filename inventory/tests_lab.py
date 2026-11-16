"""Boundary, integration and edge-case tests.

Every test follows Arrange, Act, Assert and carries the Test Case ID used in
the test report (TC_U = unit, TC_B = boundary value, TC_I = integration,
TC_E = AI-assisted edge case)."""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import reports
from .models import Order, Product, Sale, StockMovement
from .services import (
    MAX_QUANTITY, StockError, adjust, checkout, ean13, find_by_code, receive, to_decimal, to_int,
)
from .tests import make_product

User = get_user_model()


# ---------------------------------------------------------------------------
# Unit tests: equivalence partitioning (one valid class, one invalid class)
# ---------------------------------------------------------------------------
class UnitEquivalenceTests(TestCase):
    def setUp(self):
        self.rice = make_product('Rice', qty=10, price='100', cost='80', barcode='2000000000015', sku='RICE-1')

    def test_TC_U01_to_int_accepts_whole_number_text(self):
        # Arrange
        value = '5'
        # Act
        result = to_int(value)
        # Assert
        self.assertEqual(result, 5)

    def test_TC_U02_to_int_rejects_text(self):
        with self.assertRaises(StockError):
            to_int('abc')

    def test_TC_U03_to_decimal_rounds_to_two_places(self):
        self.assertEqual(to_decimal('12.5'), Decimal('12.50'))
        self.assertEqual(to_decimal('', default='7'), Decimal('7.00'))

    def test_TC_U04_to_decimal_rejects_text(self):
        with self.assertRaises(StockError):
            to_decimal('ten taka')

    def test_TC_U05_checkout_valid_cart_creates_order_and_reduces_stock(self):
        # Act
        order = checkout([{'id': self.rice.pk, 'qty': 3}], payment_method='mobile')
        # Assert
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity, 7)
        self.assertEqual(order.total, Decimal('300.00'))
        self.assertEqual(order.payment_method, 'mobile')
        sale = Sale.objects.get(order=order)
        self.assertEqual(sale.unit_cost, Decimal('80.00'))  # buy price saved for real profit

    def test_TC_U06_checkout_empty_cart_is_rejected(self):
        with self.assertRaisesMessage(StockError, 'The cart is empty.'):
            checkout([])
        self.assertEqual(Order.objects.count(), 0)

    def test_TC_U07_checkout_unknown_product_is_rejected(self):
        with self.assertRaises(StockError):
            checkout([{'id': 99999, 'qty': 1}])
        self.assertEqual(Order.objects.count(), 0)

    def test_TC_U08_receive_adds_stock_and_updates_buy_price(self):
        lines, units = receive([{'id': self.rice.pk, 'qty': 20, 'cost': '85'}])
        self.rice.refresh_from_db()
        self.assertEqual((lines, units), (1, 20))
        self.assertEqual(self.rice.quantity, 30)
        self.assertEqual(self.rice.cost_price, Decimal('85.00'))

    def test_TC_U09_adjust_damage_reduces_stock_with_reason(self):
        adjust([{'id': self.rice.pk, 'delta': -2}], reason='damage', note='Bag torn')
        self.rice.refresh_from_db()
        movement = self.rice.movements.latest('date')
        self.assertEqual(self.rice.quantity, 8)
        self.assertEqual((movement.kind, movement.reason, movement.quantity), ('adjust', 'damage', -2))

    def test_TC_U10_find_by_code_matches_barcode_and_sku(self):
        self.assertEqual(find_by_code('2000000000015'), self.rice)
        self.assertEqual(find_by_code('rice-1'), self.rice)  # SKU is case-insensitive
        self.assertIsNone(find_by_code('   '))
        self.assertIsNone(find_by_code('no-such-code'))

    def test_TC_U11_ean13_check_digit(self):
        # Worked by hand: 2x1 + 1x3 = 5, check digit = (10 - 5) % 10 = 5
        self.assertEqual(ean13('200000000001'), '2000000000015')


# ---------------------------------------------------------------------------
# Boundary value tests: on, just inside and just outside each limit
# ---------------------------------------------------------------------------
class BoundaryValueTests(TestCase):
    def setUp(self):
        self.oil = make_product('Oil', qty=10, price='50', cost='40', low_stock_threshold=5)

    def test_TC_B01_sell_exactly_all_stock(self):
        checkout([{'id': self.oil.pk, 'qty': 10}])
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity, 0)

    def test_TC_B02_sell_one_more_than_stock_is_rejected(self):
        with self.assertRaises(StockError):
            checkout([{'id': self.oil.pk, 'qty': 11}])
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity, 10)

    def test_TC_B03_quantity_zero_is_rejected_and_one_is_accepted(self):
        with self.assertRaisesMessage(StockError, 'at least 1'):
            checkout([{'id': self.oil.pk, 'qty': 0}])
        checkout([{'id': self.oil.pk, 'qty': 1}])
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity, 9)

    def test_TC_B04_low_stock_alert_starts_exactly_at_threshold(self):
        self.oil.quantity = 6
        self.assertFalse(self.oil.is_low_stock)   # threshold + 1
        self.oil.quantity = 5
        self.assertTrue(self.oil.is_low_stock)    # threshold
        self.oil.quantity = 4
        self.assertTrue(self.oil.is_low_stock)    # threshold - 1

    def test_TC_B05_sale_that_crosses_threshold_raises_alert(self):
        checkout([{'id': self.oil.pk, 'qty': 4}])       # 10 -> 6: not low yet
        self.oil.refresh_from_db()
        self.assertFalse(self.oil.is_low_stock)
        checkout([{'id': self.oil.pk, 'qty': 1}])       # 6 -> 5: now low
        self.oil.refresh_from_db()
        self.assertTrue(self.oil.is_low_stock)

    def test_TC_B06_discount_limits(self):
        full = checkout([{'id': self.oil.pk, 'qty': 1}], discount='50')
        over = checkout([{'id': self.oil.pk, 'qty': 1}], discount='80')
        negative = checkout([{'id': self.oil.pk, 'qty': 1}], discount='-10')
        self.assertEqual(full.total, Decimal('0.00'))
        self.assertEqual(over.discount, Decimal('50.00'))   # capped at the subtotal
        self.assertEqual(negative.discount, Decimal('0.00'))  # never below zero

    def test_TC_B07_amount_paid_exact_and_one_paisa_short(self):
        order = checkout([{'id': self.oil.pk, 'qty': 2}], paid='100.00')
        self.assertEqual(order.change, Decimal('0.00'))
        with self.assertRaises(StockError):
            checkout([{'id': self.oil.pk, 'qty': 2}], paid='99.99')

    def test_TC_B08_stock_count_to_zero_allowed_negative_rejected(self):
        adjust([{'id': self.oil.pk, 'counted': 0}], reason='count')
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity, 0)
        with self.assertRaises(StockError):
            adjust([{'id': self.oil.pk, 'counted': -1}], reason='count')

    def test_TC_B09_receive_quantity_limits(self):
        with self.assertRaises(StockError):
            receive([{'id': self.oil.pk, 'qty': 0}])
        receive([{'id': self.oil.pk, 'qty': MAX_QUANTITY}])
        with self.assertRaises(StockError):
            receive([{'id': self.oil.pk, 'qty': MAX_QUANTITY + 1}])

    def test_TC_B10_product_at_alert_level_appears_in_reorder_plan(self):
        # No sales at all, stock exactly at the alert level (5 of 5).
        self.oil.quantity = 5
        self.oil.save()
        today = reports.today()
        plan = reports.reorder_suggestions(today, today, cover_days=14)
        row = next((r for r in plan if r['product'].pk == self.oil.pk), None)
        self.assertIsNotNone(row, 'A product with the red low-stock badge must be in the reorder plan.')
        self.assertGreaterEqual(row['suggest'], 1)

    def test_TC_B11_reorder_quantity_matches_formula(self):
        # 14 sold in the last 7 days -> 2 per day; target = 2 x 14 + 5 = 33; stock 10 -> order 23
        for _ in range(2):                                   # sell 7, restock 7, twice
            checkout([{'id': self.oil.pk, 'qty': 7}])
            receive([{'id': self.oil.pk, 'qty': 7}])
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity, 10)
        end = reports.today()
        start = date.fromordinal(end.toordinal() - 6)
        row = next(r for r in reports.reorder_suggestions(start, end, cover_days=14) if r['product'].pk == self.oil.pk)
        self.assertEqual(row['per_day'], 2)
        self.assertEqual(row['suggest'], 23)


# ---------------------------------------------------------------------------
# Integration tests: whole flows through URLs, views, services and database
# ---------------------------------------------------------------------------
class IntegrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@shop.com', 'admin123')
        self.tea = make_product('Tea', qty=8, price='120', cost='90', low_stock_threshold=5, barcode='2000000000022')

    def post_json(self, name, payload):
        return self.client.post(reverse(name), data=json.dumps(payload), content_type='application/json')

    def test_TC_I01_valid_login_opens_dashboard(self):
        response = self.client.post(reverse('login'), {'username': 'admin', 'password': 'admin123'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.resolver_match.url_name, 'dashboard')

    def test_TC_I02_wrong_password_is_refused(self):
        response = self.client.post(reverse('login'), {'username': 'admin', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_TC_I03_empty_login_fields_show_errors(self):
        response = self.client.post(reverse('login'), {'username': '', 'password': ''})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_TC_I04_sql_injection_login_is_denied(self):
        response = self.client.post(reverse('login'), {'username': "' OR 1=1 --", 'password': "' OR 1=1 --"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_TC_I05_pages_need_login(self):
        response = self.client.get(reverse('pos'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_TC_I06_full_sale_flow_scan_pay_receipt_stock_alert(self):
        self.client.force_login(self.admin)
        # 1. scan the barcode
        found = self.client.get(reverse('api_product_lookup') + '?code=2000000000022').json()
        self.assertEqual(found['product']['id'], self.tea.pk)
        # 2. check out 3 with bKash
        data = self.post_json('pos_checkout', {
            'items': [{'id': self.tea.pk, 'qty': 3}], 'payment': 'mobile', 'paid': '360',
            'customer': {'name': 'Nusrat', 'phone': '01711000000'},
        }).json()
        self.assertTrue(data['ok'], data)
        # 3. receipt opens and shows the product
        receipt = self.client.get(data['receipt_url'])
        self.assertContains(receipt, 'Tea')
        # 4. stock went down and was logged
        self.tea.refresh_from_db()
        self.assertEqual(self.tea.quantity, 5)
        self.assertEqual(self.tea.movements.filter(reason='sale').get().stock_after, 5)
        # 5. the dashboard now lists Tea under stock alerts
        dashboard = self.client.get(reverse('dashboard'))
        self.assertIn(self.tea, list(dashboard.context['low_stock']))

    def test_TC_I07_stock_in_clears_the_alert(self):
        self.client.force_login(self.admin)
        checkout([{'id': self.tea.pk, 'qty': 4}])           # 8 -> 4, low
        response = self.post_json('stock_receive', {'lines': [{'id': self.tea.pk, 'qty': 10, 'cost': '95'}]})
        self.assertTrue(response.json()['ok'])
        self.tea.refresh_from_db()
        self.assertEqual(self.tea.quantity, 14)
        self.assertFalse(self.tea.is_low_stock)
        history = self.client.get(reverse('stock') + '?tab=history')
        self.assertEqual(history.status_code, 200)

    def test_TC_I08_report_uses_buy_price_at_time_of_sale(self):
        self.client.force_login(self.admin)
        checkout([{'id': self.tea.pk, 'qty': 2}])            # profit (120 - 90) x 2 = 60
        receive([{'id': self.tea.pk, 'qty': 1, 'cost': '200'}])  # later price rise must not change old profit
        today = reports.today()
        summary = reports.summary(today, today)
        self.assertEqual(summary['revenue'], Decimal('240.00'))
        self.assertEqual(summary['profit'], Decimal('60.00'))
        csv = self.client.get(reverse('report_export') + '?range=today')
        self.assertEqual(csv.status_code, 200)
        self.assertIn('text/csv', csv['Content-Type'])

    def test_TC_I09_cashier_cannot_open_admin_settings(self):
        cashier = User.objects.create_user('cashier', 'cashier@shop.com', 'Counter-2026!x', is_staff=True)
        self.client.force_login(cashier)
        response = self.client.get(reverse('settings_user_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse('pos')).status_code, 200)  # but can sell

    def test_TC_I10_search_with_sql_text_is_safe(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('api_product_search') + "?q=' OR 1=1 --")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])
        self.assertEqual(Product.objects.count(), 1)


# ---------------------------------------------------------------------------
# AI-assisted edge cases (Step 2/3). Each expected value was checked by hand
# against the shop's rules before it was kept.
# ---------------------------------------------------------------------------
class EdgeCaseTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@shop.com', 'admin123')
        self.client.force_login(self.admin)
        self.salt = make_product('Salt', qty=10, price='40', cost='30')

    def post_json(self, name, payload):
        return self.client.post(reverse(name), data=json.dumps(payload), content_type='application/json')

    def assertRejected(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertEqual(Order.objects.count(), 0)
        self.salt.refresh_from_db()
        self.assertEqual(self.salt.quantity, 10)

    def test_TC_E01_fractional_quantity_is_rejected(self):
        self.assertRejected(self.post_json('pos_checkout', {'items': [{'id': self.salt.pk, 'qty': 1.5}]}))

    def test_TC_E02_true_false_quantity_is_rejected(self):
        self.assertRejected(self.post_json('pos_checkout', {'items': [{'id': self.salt.pk, 'qty': True}]}))

    def test_TC_E03_items_not_a_list_returns_400_not_crash(self):
        self.assertRejected(self.post_json('pos_checkout', {'items': 'abc'}))
        self.assertRejected(self.post_json('pos_checkout', {'items': {'id': self.salt.pk}}))

    def test_TC_E04_customer_as_plain_text_returns_400(self):
        self.assertRejected(self.post_json('pos_checkout', {
            'items': [{'id': self.salt.pk, 'qty': 1}], 'customer': 'Rahim'}))

    def test_TC_E05_nan_and_infinity_amounts_are_rejected(self):
        for field in ('discount', 'paid'):
            for bad in ('NaN', 'Infinity'):
                with self.subTest(field=field, value=bad):
                    self.assertRejected(self.post_json('pos_checkout', {
                        'items': [{'id': self.salt.pk, 'qty': 1}], field: bad}))
        response = self.post_json('stock_receive', {'lines': [{'id': self.salt.pk, 'qty': 1, 'cost': 'NaN'}]})
        self.assertEqual(response.status_code, 400)

    def test_TC_E06_huge_quantity_is_rejected(self):
        response = self.post_json('stock_receive', {'lines': [{'id': self.salt.pk, 'qty': 10 ** 30, 'cost': '1'}]})
        self.assertEqual(response.status_code, 400)
        self.salt.refresh_from_db()
        self.assertEqual(self.salt.quantity, 10)

    def test_TC_E07_stock_lines_not_a_list_return_400(self):
        self.assertEqual(self.post_json('stock_receive', {'lines': 'xyz'}).status_code, 400)
        self.assertEqual(self.post_json('stock_adjust', {'reason': 'count', 'lines': 5}).status_code, 400)

    def test_TC_E08_report_with_extreme_dates_still_opens(self):
        for query in ('start=2026-01-01&end=9999-12-31', 'start=0001-01-01&end=2026-01-01'):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(reverse('report') + '?range=custom&' + query).status_code, 200)
                self.assertEqual(self.client.get(reverse('report_export') + '?range=custom&' + query).status_code, 200)
        key, start, end = reports.parse_range({'range': 'custom', 'start': '0001-01-01', 'end': '9999-12-31'})
        self.assertLess((end - start).days, reports.MAX_DAYS)

    def test_TC_E09_same_product_twice_is_merged_into_one_line(self):
        order = checkout([{'id': self.salt.pk, 'qty': 2}, {'id': self.salt.pk, 'qty': 3}])
        self.assertEqual(Sale.objects.get(order=order).quantity_sold, 5)

    def test_TC_E10_failed_checkout_changes_nothing(self):
        sugar = make_product('Sugar', qty=1, price='130', cost='110')
        with self.assertRaises(StockError):
            checkout([{'id': self.salt.pk, 'qty': 2}, {'id': sugar.pk, 'qty': 2}])
        self.salt.refresh_from_db()
        self.assertEqual(self.salt.quantity, 10)  # the first line was rolled back too
        self.assertEqual(StockMovement.objects.filter(reason='sale').count(), 0)


# ---------------------------------------------------------------------------
# Step 3 gap tests: parts the first run left uncovered (people, categories,
# Telegram without settings, product edit/delete).
# ---------------------------------------------------------------------------
class GapTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'admin@shop.com', 'admin123')
        self.client.force_login(self.admin)

    def test_TC_G01_customer_add_edit_delete(self):
        from .models import Customer
        self.assertEqual(self.client.post(reverse('customer_create'),
                         {'name': 'Rahim', 'phone': '01811111111', 'address': 'Dhaka'}).status_code, 302)
        customer = Customer.objects.get(phone='01811111111')
        self.client.post(reverse('customer_update', args=[customer.pk]),
                         {'name': 'Rahim Uddin', 'phone': '01811111111', 'address': 'Sherpur'})
        customer.refresh_from_db()
        self.assertEqual((customer.name, customer.address), ('Rahim Uddin', 'Sherpur'))
        self.assertEqual(self.client.get(reverse('customer_detail', args=[customer.pk])).status_code, 200)
        self.client.post(reverse('customer_delete', args=[customer.pk]))
        self.assertFalse(Customer.objects.filter(pk=customer.pk).exists())

    def test_TC_G02_supplier_add_edit_delete(self):
        from .models import Supplier
        self.client.post(reverse('supplier_create'), {'name': 'ACI Ltd', 'phone': '029999', 'address': 'Tejgaon'})
        supplier = Supplier.objects.get(name='ACI Ltd')
        self.client.post(reverse('supplier_update', args=[supplier.pk]),
                         {'name': 'ACI Limited', 'phone': '029999', 'address': 'Tejgaon'})
        supplier.refresh_from_db()
        self.assertEqual(supplier.name, 'ACI Limited')
        self.client.post(reverse('supplier_delete', args=[supplier.pk]))
        self.assertFalse(Supplier.objects.filter(pk=supplier.pk).exists())

    def test_TC_G03_category_in_use_cannot_be_deleted(self):
        product = make_product('Rice')
        response = self.client.post(reverse('category_delete', args=[product.category.pk]), follow=True)
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertIsNotNone(product.category_id)

    def test_TC_G04_telegram_without_settings_shows_error(self):
        response = self.client.post(reverse('report_telegram'), {'range': 'today'}, follow=True)
        messages = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Telegram' in m for m in messages), messages)

    def test_TC_G05_product_edit_and_delete(self):
        product = make_product('Lentil', qty=0, price='110', cost='95')
        response = self.client.post(reverse('product_update', args=[product.pk]), {
            'name': 'Lentil (Masur)', 'category': product.category.pk, 'cost_price': '95', 'price': '115',
            'quantity': '0', 'low_stock_threshold': '3', 'sku': product.sku or '', 'barcode': product.barcode or '',
        })
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual((product.name, product.price), ('Lentil (Masur)', Decimal('115.00')))
        self.client.post(reverse('product_delete', args=[product.pk]))
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())
