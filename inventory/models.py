from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'phone']

    def __str__(self):
        return self.name or self.phone or f'Customer #{self.pk}'


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField('SKU', max_length=50, blank=True, db_index=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='products',
    )
    cost_price = models.DecimalField('buy price', max_digits=10, decimal_places=2, default=0)
    price = models.DecimalField('sell price', max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    @property
    def profit_per_unit(self):
        return self.price - self.cost_price

    @property
    def stock_value(self):
        """What the current stock cost to buy."""
        return self.cost_price * self.quantity

    def as_json(self):
        """Shape used by the POS / stock screens."""
        return {
            'id': self.pk,
            'name': self.name,
            'sku': self.sku,
            'barcode': self.barcode,
            'price': str(self.price),
            'cost': str(self.cost_price),
            'qty': self.quantity,
            'low': self.is_low_stock,
            'category': self.category.name if self.category_id else '',
            'supplier_id': self.supplier_id,
        }


class StockIn(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_ins')
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_ins',
    )
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'stock in'
        verbose_name_plural = 'stock in records'

    def __str__(self):
        return f'{self.product.name} + {self.quantity}'

    @property
    def total_cost(self):
        return self.unit_cost * self.quantity


class Order(models.Model):
    """One POS checkout — the receipt. Each product line is a Sale."""
    PAYMENT_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile', 'bKash / Nagad'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cash')
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'Receipt #{self.pk}'

    @property
    def change(self):
        return max(self.paid - self.total, Decimal('0'))


class Sale(models.Model):
    """One product line of an Order."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales')
    quantity_sold = models.PositiveIntegerField()
    # Sell price of one unit before any order discount, as printed on the receipt.
    list_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # What this line actually brought in, after its share of the order discount.
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    # Buy price of one unit at the moment of the sale, so later price changes
    # don't rewrite past profit.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if not self.total_price:
            self.total_price = self.product.price * self.quantity_sold
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product.name} × {self.quantity_sold}'

    @property
    def unit_price(self):
        if not self.quantity_sold:
            return Decimal('0')
        return self.total_price / self.quantity_sold

    @property
    def list_total(self):
        return self.list_price * self.quantity_sold

    @property
    def profit(self):
        return self.total_price - self.unit_cost * self.quantity_sold


class StockMovement(models.Model):
    """The stock ledger: one row for every change to a product's quantity."""
    KIND_CHOICES = [
        ('in', 'Stock in'),
        ('out', 'Stock out'),
        ('adjust', 'Adjustment'),
    ]
    REASON_CHOICES = [
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('count', 'Stock count'),
        ('damage', 'Damaged'),
        ('expired', 'Expired'),
        ('lost', 'Lost / theft'),
        ('return', 'Customer return'),
        ('opening', 'Opening stock'),
        ('other', 'Other'),
    ]
    ADJUST_REASONS = ['count', 'damage', 'expired', 'lost', 'return', 'other']

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    quantity = models.IntegerField(help_text='Signed change: positive adds stock, negative removes it.')
    stock_after = models.IntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-date', '-pk']

    def __str__(self):
        return f'{self.product.name} {self.quantity:+d}'

    @property
    def value(self):
        return self.unit_cost * abs(self.quantity)


class StoreSettings(models.Model):
    """Single row of shop-wide settings, edited from the Settings page."""
    shop_name = models.CharField(max_length=120, default='Smart Inventory')
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    receipt_footer = models.CharField(max_length=255, default='Thank you for shopping with us!')
    default_low_stock = models.PositiveIntegerField('default low stock alert', default=5)
    reorder_cover_days = models.PositiveIntegerField(
        default=14, help_text='Reorder suggestions keep this many days of sales in stock.',
    )
    telegram_bot_token = models.CharField(max_length=120, blank=True)
    telegram_chat_id = models.CharField(max_length=60, blank=True)

    class Meta:
        verbose_name = 'store settings'
        verbose_name_plural = 'store settings'

    def __str__(self):
        return self.shop_name

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def telegram_ready(self):
        return bool(self.telegram_bot_token and self.telegram_chat_id)
