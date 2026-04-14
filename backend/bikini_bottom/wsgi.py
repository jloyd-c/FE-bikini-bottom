"""
WSGI config for bikini_bottom project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bikini_bottom.settings.dev')
application = get_wsgi_application()
