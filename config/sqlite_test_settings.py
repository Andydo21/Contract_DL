"""Fast local test settings: in-memory SQLite, no migrations. Usage: python manage.py test --settings=config.sqlite_test_settings"""
from config.settings import *  # noqa
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'},
             'workflow': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


class _NoMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _NoMigrations()
