from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.db.models import Q

from .models import Category, Customer, Product, StoreSettings, Supplier

User = get_user_model()


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'sku', 'barcode', 'category', 'supplier',
            'cost_price', 'price', 'quantity', 'low_stock_threshold',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Miniket Rice 5kg'}),
            'sku': forms.TextInput(attrs={'class': 'form-control mono', 'placeholder': 'Auto if empty'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control mono', 'placeholder': 'Scan or leave empty to generate'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].empty_label = '— No supplier —'
        self.fields['category'].empty_label = 'Select a category'
        if self.instance.pk:
            # Quantity changes on an existing product go through Stock In / Adjustment
            # so the ledger stays complete.
            del self.fields['quantity']
        else:
            self.fields['low_stock_threshold'].initial = StoreSettings.load().default_low_stock
            self.fields['quantity'].label = 'Opening stock'

    def _clean_code(self, field):
        value = self.cleaned_data.get(field, '').strip()
        if value and Product.objects.filter(**{f'{field}__iexact': value}).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(f'Another product already uses this {self.fields[field].label}.')
        return value

    def clean_sku(self):
        return self._clean_code('sku')

    def clean_barcode(self):
        return self._clean_code('barcode')

    def clean(self):
        cleaned = super().clean()
        cost, price = cleaned.get('cost_price'), cleaned.get('price')
        if cost is not None and price is not None and price < cost:
            self.add_error('price', 'Sell price is lower than the buy price — this product would sell at a loss.')
        return cleaned


class StockInForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'autofocus': True}),
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.all(),
        required=False,
        empty_label='— No supplier —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    unit_cost = forms.DecimalField(
        label='Buy price per unit',
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
    )


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Rahman Traders'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 01711-000000'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kawran Bazar, Dhaka'}),
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Nusrat Jahan'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 01711-000000'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'optional'}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('name') and not cleaned.get('phone'):
            raise forms.ValidationError('Enter at least a name or a phone number.')
        phone = cleaned.get('phone')
        if phone and Customer.objects.filter(phone=phone).exclude(pk=self.instance.pk).exists():
            self.add_error('phone', 'Another customer already has this phone number.')
        return cleaned


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Snacks'}),
        }


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class StoreSettingsForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = ['shop_name', 'phone', 'address', 'receipt_footer', 'default_low_stock', 'reorder_cover_days']
        widgets = {
            'shop_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Shown on receipts'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Shown on receipts'}),
            'receipt_footer': forms.TextInput(attrs={'class': 'form-control'}),
            'default_low_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'reorder_cover_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '180'}),
        }

    def clean_reorder_cover_days(self):
        days = self.cleaned_data['reorder_cover_days']
        if not 1 <= days <= 180:
            raise forms.ValidationError('Choose between 1 and 180 days.')
        return days


class TelegramForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = ['telegram_bot_token', 'telegram_chat_id']
        labels = {'telegram_bot_token': 'Bot token', 'telegram_chat_id': 'Chat ID'}
        widgets = {
            'telegram_bot_token': forms.PasswordInput(
                render_value=True, attrs={'class': 'form-control mono', 'placeholder': '123456789:ABC…', 'autocomplete': 'off'},
            ),
            'telegram_chat_id': forms.TextInput(attrs={'class': 'form-control mono', 'placeholder': 'e.g. -1001234567890'}),
        }


def _unique_identity(form, field, value):
    if value and User.objects.filter(**{f'{field}__iexact': value}).exclude(pk=getattr(form.instance, 'pk', None)).exists():
        raise forms.ValidationError(f'Another account already uses this {field}.')
    return value


class AccountForm(forms.ModelForm):
    """Change your own username, name and email."""

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

    def clean_username(self):
        return _unique_identity(self, 'username', self.cleaned_data['username'])

    def clean_email(self):
        return _unique_identity(self, 'email', self.cleaned_data['email'].strip().lower())


class _PasswordPairMixin:
    def _check_pair(self, user):
        p1, p2 = self.cleaned_data.get('new_password1'), self.cleaned_data.get('new_password2')
        if p1 and p2 and p1 != p2:
            self.add_error('new_password2', 'The two passwords don’t match.')
        elif p1:
            try:
                password_validation.validate_password(p1, user)
            except forms.ValidationError as error:
                self.add_error('new_password1', error)


PASSWORD_WIDGET = forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'})


class AdminUserForm(_PasswordPairMixin, forms.ModelForm):
    """Add a new admin/staff account, or edit one (password optional when editing)."""
    ROLE_CHOICES = [
        ('admin', 'Admin — full access incl. settings'),
        ('staff', 'Staff — POS, stock and reports only'),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    new_password1 = forms.CharField(label='Password', widget=PASSWORD_WIDGET, required=False)
    new_password2 = forms.CharField(label='Confirm password', widget=PASSWORD_WIDGET, required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
        labels = {'is_active': 'Account is active (can sign in)'}
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self.fields['email'].required = True
        if self.instance.pk:
            self.fields['role'].initial = 'admin' if self.instance.is_superuser else 'staff'
            self.fields['new_password1'].help_text = 'Leave empty to keep the current password.'
        else:
            self.fields['new_password1'].required = True
            self.fields['new_password2'].required = True
            self.fields['is_active'].initial = True
        if editor and self.instance.pk == editor.pk:
            # Nobody can lock themselves out from this screen.
            del self.fields['role']
            del self.fields['is_active']

    def clean_username(self):
        return _unique_identity(self, 'username', self.cleaned_data['username'])

    def clean_email(self):
        return _unique_identity(self, 'email', self.cleaned_data['email'].strip().lower())

    def clean(self):
        cleaned = super().clean()
        self._check_pair(self.instance)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if 'role' in self.cleaned_data:
            admin = self.cleaned_data['role'] == 'admin'
            user.is_superuser = admin
            user.is_staff = True
        if self.cleaned_data.get('new_password1'):
            user.set_password(self.cleaned_data['new_password1'])
        if commit:
            user.save()
        return user


def other_active_admins(user):
    return User.objects.filter(is_superuser=True, is_active=True).filter(~Q(pk=user.pk))
