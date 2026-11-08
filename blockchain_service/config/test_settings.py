from .settings import *

# Current model schema only; never connect to the deployed Neon databases.
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
MIGRATION_MODULES = {'blockchain': None}
MIDDLEWARE = []
