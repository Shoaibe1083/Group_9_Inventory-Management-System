#!/bin/bash
# One-shot setup for Smart Inventory:
# migrations -> superuser (admin/admin123) -> sample data
set -e
cd "$(dirname "$0")"

PYTHON=${PYTHON:-./venv/bin/python}

$PYTHON manage.py migrate
$PYTHON manage.py createsu
$PYTHON manage.py seed

echo ""
echo "Setup complete. Start the server with:"
echo "  ./venv/bin/python manage.py runserver"
