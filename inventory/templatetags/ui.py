from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()


def _number(value):
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError):
        return Decimal('0')


@register.filter
def money(value, places=2):
    """৳1,234.50 — negative values keep the sign in front."""
    amount = _number(value)
    text = f'{abs(amount):,.{int(places)}f}'
    return f'{"-" if amount < 0 else ""}৳{text}'


@register.filter
def money0(value):
    return money(value, 0)


@register.filter
def num(value, places=0):
    return f'{_number(value):,.{int(places)}f}'


@register.filter
def absval(value):
    return abs(value) if value is not None else 0


@register.filter
def initials(value):
    words = [w for w in str(value or '').replace('-', ' ').split() if w[:1].isalnum()]
    return ''.join(w[0] for w in words[:2]).upper() or '•'


@register.filter
def percent_of(value, total):
    total = _number(total)
    return float(_number(value) / total * 100) if total else 0


@register.simple_tag
def delta(value, suffix='%', invert=False):
    """Coloured change pill. `value` is a percent (or points) change, or None."""
    if value is None:
        return format_html('<span class="delta flat">new</span>')
    good = value >= 0 if not invert else value <= 0
    if abs(value) < 0.05:
        return format_html('<span class="delta flat">0{}</span>', suffix)
    icon = 'bi-arrow-up-short' if value > 0 else 'bi-arrow-down-short'
    return format_html(
        '<span class="delta {}"><i class="bi {}"></i>{}{}</span>',
        'up' if good else 'down', icon, f'{abs(value):.1f}', suffix,
    )


@register.simple_tag
def page_range(page_obj):
    """Compact page list: 1 … 4 5 [6] 7 8 … 20"""
    current, last = page_obj.number, page_obj.paginator.num_pages
    pages = sorted({1, last, *range(max(1, current - 2), min(last, current + 2) + 1)})
    out, prev = [], 0
    for p in pages:
        if p - prev > 1:
            out.append(None)
        out.append(p)
        prev = p
    return out
