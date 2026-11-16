import csv
import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect


def admin_required(view):
    """Logged in *and* an admin (superuser). Staff get bounced with a message."""
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Only admins can open that page.')
            return redirect('dashboard')
        return view(request, *args, **kwargs)
    return wrapper


def json_body(request):
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def json_error(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


def csv_response(filename):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # lets Excel read the file as UTF-8
    return response, csv.writer(response)


def querystring(request, **changes):
    """Current GET params with some replaced — for pagination links."""
    params = request.GET.copy()
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
