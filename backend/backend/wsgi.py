"""
WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from .startup import ensure_schema_ready

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

ensure_schema_ready()

application = get_wsgi_application()
