from django.db.models import F

from .models import Product, StoreSettings

SECTIONS = [
    # (url_name prefix, sidebar section)
    ('dashboard', 'dashboard'),
    ('pos', 'pos'),
    ('alert', 'alerts'),
    ('stock', 'stock'),
    ('product', 'products'),
    ('order', 'sales'),
    ('sale', 'sales'),
    ('customer', 'customers'),
    ('supplier', 'suppliers'),
    ('category', 'categories'),
    ('report', 'reports'),
    ('settings', 'settings'),
]


def nav_section(request):
    """Tell the sidebar which menu item to highlight."""
    match = getattr(request, 'resolver_match', None)
    name = match.url_name if match else ''
    section = next((s for prefix, s in SECTIONS if name and name.startswith(prefix)), '')
    return {'nav_section': section}


THEMES = [
    # (key, name, description, preview colours: sidebar, background, surface, accent)
    ('navy', 'Navy', 'Navy sidebar, bright workspace', ('#0C1A3A', '#F4F6FA', '#FFFFFF', '#1F3A8A')),
    ('midnight', 'Midnight', 'Dark navy, easy on the eyes', ('#070E1D', '#0A1224', '#101B34', '#5B7FF0')),
    ('sage', 'Sage', 'Warm paper with green accents', ('#FBFAF6', '#F6F5F0', '#FFFFFF', '#2F7A55')),
]
THEME_COOKIE = 'si_theme'


def store(request):
    theme = request.COOKIES.get(THEME_COOKIE, 'navy')
    context = {
        'store': StoreSettings.load(),
        'theme': theme if theme in {t[0] for t in THEMES} else 'navy',
        'themes': THEMES,
    }
    if getattr(request, 'user', None) and request.user.is_authenticated:
        context['nav_low_stock'] = Product.objects.filter(quantity__lte=F('low_stock_threshold')).count()
    return context
