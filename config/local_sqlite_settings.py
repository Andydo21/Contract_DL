"""Local fallback while the shared PostgreSQL (Neon) is unavailable: same app on SQLite files in local_db/.

Opt-in only; the default settings still use PostgreSQL from .env.
    $env:DJANGO_SETTINGS_MODULE = "config.local_sqlite_settings"
    python manage.py migrate --run-syncdb     # first run: create the tables
    python manage.py createsuperuser
    python manage.py runserver 127.0.0.1:8020
"""
from config.settings import *  # noqa: F401,F403
from config.settings import BASE_DIR

LOCAL_DB_DIR = BASE_DIR / 'local_db'
LOCAL_DB_DIR.mkdir(exist_ok=True)
DATABASES = {
    'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': LOCAL_DB_DIR / 'default.sqlite3'},
    'workflow': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': LOCAL_DB_DIR / 'workflow.sqlite3'},
}
# Historical migrations contain PostgreSQL-only SQL; --run-syncdb creates the current tables directly.
MIGRATION_MODULES = {'contracts': None, 'ai_extract': None}
MEDIA_ROOT = LOCAL_DB_DIR / 'media'
