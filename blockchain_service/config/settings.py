import os
from pathlib import Path
from dotenv import load_dotenv

import sys
BASE_DIR = Path(__file__).resolve().parent.parent

# Make shared/ importable from project root
shared_parent = str(BASE_DIR.parent)
if shared_parent not in sys.path:
    sys.path.insert(0, shared_parent)

# Load shared root .env so SECRET_KEY matches main Django app
env_path = BASE_DIR.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-default-change-me")

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'blockchain',
]

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'shared.jwt_middleware.JWTMiddleware',
]

ROOT_URLCONF = 'config.urls'

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'blockchain_db'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'postgrespassword'),
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': os.environ.get('DB_SSLMODE', 'disable'),
        }
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
