# AudioXCore/settings.py

from pathlib import Path
import os
from dotenv import load_dotenv
import logging
import logging.config
from django.core.exceptions import ImproperlyConfigured

# Basic logging setup (can be configured further below)
logging.basicConfig(level=logging.INFO, format='{levelname} {asctime} {name} {message}', style='{')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / '.env'

if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path, override=True)
    # logger.info(f"Loaded environment variables from: {dotenv_path}") # Removed for brevity
else:
    logger.warning(f"WARNING: .env file not found at {dotenv_path}.")

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'

if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): DJANGO_SECRET_KEY not set.")
elif not SECRET_KEY and DEBUG:
    logger.warning("Warning (DEBUG): DJANGO_SECRET_KEY not set. Using insecure dummy key.")
    SECRET_KEY = 'django-insecure-dummy-key-for-debug-set-a-real-one'

ALLOWED_HOSTS_STRING = os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost' if DEBUG else None)
if not ALLOWED_HOSTS_STRING and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): DJANGO_ALLOWED_HOSTS not set.")

ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',') if host.strip()] if ALLOWED_HOSTS_STRING else []
if DEBUG:
    ALLOWED_HOSTS.extend(['127.0.0.1', 'localhost'])
    ALLOWED_HOSTS = list(set(ALLOWED_HOSTS))

# logger.info(f"DEBUG mode is {'ON' if DEBUG else 'OFF'}") # Removed for brevity

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'AudioXApp',
    'django.contrib.humanize',
    'mathfilters',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'AudioXCore.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'AudioXCore.wsgi.application'

# --- Database Configuration ---
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', '127.0.0.1' if DEBUG else None)
DB_PORT = os.getenv('DB_PORT', '5432' if DEBUG else None)
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'public')

if not all([DB_NAME, DB_USER, DB_PASSWORD, DB_HOST]) and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): Database connection details missing.")

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}
if DB_ENGINE == 'django.db.backends.postgresql' and DB_SCHEMA:
    DATABASES['default']['OPTIONS'] = {'options': f'-c search_path={DB_SCHEMA},public'}

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': { 'min_length': 8 }},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_collected')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'), # Corrected path
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
os.makedirs(STATIC_ROOT, exist_ok=True)

# --- Media files ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
os.makedirs(MEDIA_ROOT, exist_ok=True)

# --- Default primary key ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Custom User Model ---
AUTH_USER_MODEL = 'AudioXApp.User'
LOGIN_URL = '/login/'

# --- Email Configuration ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]):
    logger.warning("Email settings not fully configured. Email features may fail.")

# --- Caching ---
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'audiox-local-cache',
    }
}

# --- Stripe Configuration ---
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Renamed variable and updated getenv key
STRIPE_PRICE_ID_COINS_250 = os.getenv('STRIPE_PRICE_ID_COINS_250')
STRIPE_PRICE_ID_COINS_500 = os.getenv('STRIPE_PRICE_ID_COINS_500')
STRIPE_PRICE_ID_COINS_1000 = os.getenv('STRIPE_PRICE_ID_COINS_1000')
STRIPE_PRICE_ID_SUB_MONTHLY = os.getenv('STRIPE_PRICE_ID_SUB_MONTHLY')
STRIPE_PRICE_ID_SUB_ANNUAL = os.getenv('STRIPE_PRICE_ID_SUB_ANNUAL')

if not all([STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY]) and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): Stripe keys missing.")
if not STRIPE_WEBHOOK_SECRET:
    raise ImproperlyConfigured("CRITICAL: Stripe Webhook Secret missing.")
# Updated check to include the new 250 coin variable
if not all([STRIPE_PRICE_ID_COINS_250, STRIPE_PRICE_ID_COINS_500, STRIPE_PRICE_ID_COINS_1000, STRIPE_PRICE_ID_SUB_MONTHLY, STRIPE_PRICE_ID_SUB_ANNUAL]):
    logger.warning("One or more Stripe Price IDs are missing. Purchases might fail.")

# --- Logging Configuration ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'AudioXApp': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
         'stripe': {
            'handlers': ['console'],
            'level': 'WARNING', # Less verbose for stripe by default
            'propagate': False,
        },
    },
}
logging.config.dictConfig(LOGGING)
