"""WSGI config for the Smart Inventory project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartinventory.settings')

application = get_wsgi_application()
