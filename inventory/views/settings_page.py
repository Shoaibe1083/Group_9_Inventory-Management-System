from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .. import reports
from ..forms import AccountForm, AdminUserForm, StoreSettingsForm, TelegramForm, other_active_admins
from ..models import StoreSettings
from .analytics import send_telegram
from .common import admin_required

User = get_user_model()

TABS = [
    # (key, label, icon, admin only)
    ('account', 'My account', 'bi-person-circle', False),
    ('appearance', 'Appearance', 'bi-palette', False),
    ('store', 'Store', 'bi-shop', True),
    ('users', 'Admins & staff', 'bi-people', True),
    ('telegram', 'Telegram', 'bi-telegram', True),
]


def _password_form(user, data=None):
    form = PasswordChangeForm(user, data)
    for field in form.fields.values():
        field.widget.attrs.update({'class': 'form-control'})
    return form


@login_required
def settings_page(request):
    is_admin = request.user.is_superuser
    tabs = [t for t in TABS if is_admin or not t[3]]
    tab = request.GET.get('tab', 'account')
    if tab not in {t[0] for t in tabs}:
        tab = 'account'

    store = StoreSettings.load()
    account_form = AccountForm(instance=request.user)
    password_form = _password_form(request.user)
    store_form = StoreSettingsForm(instance=store)
    telegram_form = TelegramForm(instance=store)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'account':
            account_form = AccountForm(request.POST, instance=request.user)
            if account_form.is_valid():
                account_form.save()
                messages.success(request, 'Your account details were saved.')
                return redirect(reverse('settings') + '?tab=account')
        elif action == 'password':
            password_form = _password_form(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # stay signed in
                messages.success(request, 'Your password was changed.')
                return redirect(reverse('settings') + '?tab=account')
        elif action == 'store' and is_admin:
            store_form = StoreSettingsForm(request.POST, instance=store)
            if store_form.is_valid():
                store_form.save()
                messages.success(request, 'Store settings were saved.')
                return redirect(reverse('settings') + '?tab=store')
        elif action == 'telegram' and is_admin:
            telegram_form = TelegramForm(request.POST, instance=store)
            if telegram_form.is_valid():
                telegram_form.save()
                messages.success(request, 'Telegram settings were saved.')
                return redirect(reverse('settings') + '?tab=telegram')

    return render(request, 'inventory/settings.html', {
        'tabs': tabs,
        'tab': tab,
        'account_form': account_form,
        'password_form': password_form,
        'store_form': store_form,
        'telegram_form': telegram_form,
        'users': User.objects.order_by('-is_superuser', 'username') if is_admin else [],
    })


@admin_required
def settings_user_create(request):
    form = AdminUserForm(request.POST or None, editor=request.user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'Account "{user.username}" was created. They can sign in with their username or email.')
        return redirect(reverse('settings') + '?tab=users')
    return render(request, 'inventory/settings_user_form.html', {'form': form, 'title': 'Add admin or staff'})


@admin_required
def settings_user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminUserForm(request.POST or None, instance=user, editor=request.user)
    if request.method == 'POST' and form.is_valid():
        demoting = 'role' in form.cleaned_data and (
            form.cleaned_data['role'] != 'admin' or not form.cleaned_data.get('is_active', True)
        )
        if user.is_superuser and demoting and not other_active_admins(user).exists():
            form.add_error(None, forms.ValidationError('This is the only active admin — add another admin first.'))
        else:
            form.save()
            if user.pk == request.user.pk:
                update_session_auth_hash(request, user)
            messages.success(request, f'Account "{user.username}" was updated.')
            return redirect(reverse('settings') + '?tab=users')
    return render(request, 'inventory/settings_user_form.html', {
        'form': form, 'title': f'Edit {user.username}', 'edit_user': user,
    })


@admin_required
def settings_user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, 'You can’t delete your own account.')
        return redirect(reverse('settings') + '?tab=users')
    if user.is_superuser and not other_active_admins(user).exists():
        messages.error(request, 'This is the only active admin and can’t be deleted.')
        return redirect(reverse('settings') + '?tab=users')
    if request.method == 'POST':
        name = user.username
        user.delete()
        messages.success(request, f'Account "{name}" was deleted.')
        return redirect(reverse('settings') + '?tab=users')
    return render(request, 'inventory/confirm_delete.html', {
        'object_name': user.username,
        'kind': 'account',
        'note': 'They will no longer be able to sign in. Sales they made stay in history.',
        'cancel_url': 'settings',
    })


@admin_required
@require_POST
def settings_telegram_test(request):
    store = StoreSettings.load()
    today = reports.today()
    error = send_telegram(store, reports.telegram_text(store, today, today))
    if error:
        messages.error(request, error)
    else:
        messages.success(request, 'Test message sent — check your Telegram chat.')
    return redirect(reverse('settings') + '?tab=telegram')
