"""
ASGI config for bikini_bottom project.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bikini_bottom.settings.dev')
application = get_asgi_application()
