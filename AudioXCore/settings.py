# AudioXCore/settings.py

import os
from pathlib import Path
from dotenv import load_dotenv
import logging
import logging.config
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
from decimal import Decimal

# =============================================================================
#  INITIAL SETUP & ENVIRONMENT CONFIGURATION
# =============================================================================
# --- Path Setup ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Load Environment Variables ---
# Loads variables from the .env file in the project's base directory.
dotenv_path = BASE_DIR / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    # Use a basic logger here before the full logging config is set up.
    logging.basicConfig()
    logging.warning(f"WARNING: .env file not found at {dotenv_path}.")

# =============================================================================
#  CORE DJANGO SETTINGS
# =============================================================================
# --- Security ---
# In production, SECRET_KEY and ALLOWED_HOSTS must be set in the .env file.
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'

if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): DJANGO_SECRET_KEY not set in .env file.")
elif not SECRET_KEY and DEBUG:
    SECRET_KEY = 'django-insecure-dummy-key-for-local-debug-only'
    logging.warning("Warning (DEBUG): DJANGO_SECRET_KEY not set. Using an insecure dummy key.")

ALLOWED_HOSTS_STRING = os.getenv('DJANGO_ALLOWED_HOSTS')
if not ALLOWED_HOSTS_STRING and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): DJANGO_ALLOWED_HOSTS not set in .env file.")

ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',')] if ALLOWED_HOSTS_STRING else []
if DEBUG:
    ALLOWED_HOSTS.extend(['127.0.0.1', 'localhost'])
    ALLOWED_HOSTS = list(set(ALLOWED_HOSTS)) # Ensure uniqueness

# --- Application Definition ---
INSTALLED_APPS = [
    # ASGI/Channels
    'daphne',
    'channels',

    # Django Core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',

    # Custom Application
    'AudioXApp.apps.AudioxappConfig', # Use AppConfig for signal registration

    # Third-Party Apps
    'mathfilters',
    'rest_framework',
    'rest_framework.authtoken',
    'django_celery_beat',

    # Allauth for authentication
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

# --- Middleware Configuration ---
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',          # Django Allauth middleware
    'AudioXApp.middleware.ProfileCompletionMiddleware',      # Custom middleware
]

# --- URL & Template Configuration ---
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

# --- WSGI & ASGI Application ---
WSGI_APPLICATION = 'AudioXCore.wsgi.application'
ASGI_APPLICATION = 'AudioXCore.asgi.application'

# =============================================================================
#  DATABASE CONFIGURATION
# =============================================================================
# Uses PostgreSQL connection details from the .env file.
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', '127.0.0.1' if DEBUG else None)
DB_PORT = os.getenv('DB_PORT', '5432' if DEBUG else None)
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'public')

if not all([DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT]) and not DEBUG:
    logging.warning("Warning (PRODUCTION): Database connection details may be incomplete in .env file.")

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
# Set search path for non-public PostgreSQL schemas
if DB_ENGINE == 'django.db.backends.postgresql' and DB_SCHEMA and DB_SCHEMA.lower() != 'public':
    DATABASES['default'].setdefault('OPTIONS', {})['options'] = f'-c search_path={DB_SCHEMA},public'

# --- Default primary key type ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
#  AUTHENTICATION & AUTHORIZATION
# =============================================================================
# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Custom User Model & Auth URLs ---
AUTH_USER_MODEL = 'AudioXApp.User'
LOGIN_URL = reverse_lazy('account_login')
LOGIN_REDIRECT_URL = reverse_lazy('AudioXApp:home')
LOGOUT_REDIRECT_URL = reverse_lazy('AudioXApp:home')

# --- Django Allauth Configuration ---
# NOTE: The following settings have been updated to resolve deprecation warnings.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1

# User authentication and signup settings (Updated for latest django-allauth)
# Fixed deprecation warnings
ACCOUNT_LOGIN_METHODS = {'email'}  # Replaces deprecated ACCOUNT_AUTHENTICATION_METHOD
ACCOUNT_USER_MODEL_USERNAME_FIELD = 'username'
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = os.getenv('ACCOUNT_EMAIL_VERIFICATION', 'none') # 'none', 'optional', or 'mandatory'
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_GET = True

# Updated signup fields configuration (replaces deprecated individual settings)
ACCOUNT_SIGNUP_FIELDS = {'email', 'username'}  # Replaces ACCOUNT_EMAIL_REQUIRED and ACCOUNT_USERNAME_REQUIRED

# Custom adapters for handling signup logic
ACCOUNT_ADAPTER = 'AudioXApp.adapters.CustomAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'AudioXApp.adapters.CustomSocialAccountAdapter'

# Social Account (Google) specific settings
SOCIALACCOUNT_AUTO_SIGNUP = False  # Require explicit signup first, then login
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_STORE_TOKENS = True
# Removed SOCIALACCOUNT_PROVIDERS to avoid conflicts with database configuration

# =============================================================================
#  INTERNATIONALIZATION & STATIC/MEDIA FILES
# =============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles_collected'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
os.makedirs(STATIC_ROOT, exist_ok=True)

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
os.makedirs(MEDIA_ROOT, exist_ok=True)

# =============================================================================
#  ASYNCHRONOUS, CACHING & BACKGROUND TASKS
# =============================================================================
# --- Caching Configuration ---
# Using Redis for caching in Docker environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Fallback to file-based cache if Redis is not available (development only)
if DEBUG and not os.getenv('REDIS_URL'):
    CACHE_LOCATION_PATH = BASE_DIR / 'django_cache_data'
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': CACHE_LOCATION_PATH,
            'TIMEOUT': 3600,
            'OPTIONS': {'MAX_ENTRIES': 1000}
        }
    }
    os.makedirs(CACHE_LOCATION_PATH, exist_ok=True)
    logging.warning("Warning: Using file-based cache. Set REDIS_URL for better performance.")

# --- Channels Configuration ---
# Using Redis for WebSocket connections in Docker environment
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [REDIS_URL],
        },
    },
}

# Fallback to in-memory layer if Redis is not available (development only)
if DEBUG and not os.getenv('REDIS_URL'):
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
    logging.warning("Warning: Using in-memory channel layer. Set REDIS_URL for production.")

# --- Celery Configuration ---
# Using Redis as message broker for asynchronous task processing in Docker
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')
CELERY_TASK_ALWAYS_EAGER = False  # Enable async processing with Redis

# Fallback to synchronous execution if Redis is not available (development only)
if DEBUG and not os.getenv('CELERY_BROKER_URL'):
    CELERY_TASK_ALWAYS_EAGER = True
    logging.warning("Warning: Using synchronous Celery execution. Set CELERY_BROKER_URL for async processing.")

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Additional Celery optimizations for Docker
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True

# =============================================================================
#  THIRD-PARTY SERVICES & API KEYS
# =============================================================================
# --- Email Configuration ---
EMAIL_BACKEND = os.getenv('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@audiox.com')

if EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend' and not all([EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]) and not DEBUG:
    logging.warning("Warning (PRODUCTION): SMTP Email settings are not fully configured in .env file.")

# --- Stripe Configuration ---
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
STRIPE_PRICE_ID_COINS_250 = os.getenv('STRIPE_PRICE_ID_COINS_250')
STRIPE_PRICE_ID_COINS_500 = os.getenv('STRIPE_PRICE_ID_COINS_500')
STRIPE_PRICE_ID_COINS_1000 = os.getenv('STRIPE_PRICE_ID_COINS_1000')
STRIPE_PRICE_ID_SUB_MONTHLY = os.getenv('STRIPE_PRICE_ID_SUB_MONTHLY')
STRIPE_PRICE_ID_SUB_ANNUAL = os.getenv('STRIPE_PRICE_ID_SUB_ANNUAL')

if STRIPE_SECRET_KEY:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logging.warning("Warning: Stripe API secret key is not set in .env file.")

# --- AI Service Keys (Google) ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GOOGLE_CREDENTIALS_FILE_NAME = os.getenv('GOOGLE_CREDENTIALS_FILE_NAME')
if GOOGLE_CREDENTIALS_FILE_NAME:
    GOOGLE_APPLICATION_CREDENTIALS = BASE_DIR / GOOGLE_CREDENTIALS_FILE_NAME
    if not GOOGLE_APPLICATION_CREDENTIALS.exists():
        logging.error(f"FATAL: Google credentials file '{GOOGLE_CREDENTIALS_FILE_NAME}' not found.")
else:
    GOOGLE_APPLICATION_CREDENTIALS = None
    logging.warning("Warning: GOOGLE_CREDENTIALS_FILE_NAME not set. Google Cloud services will be unavailable.")

# --- Django REST Framework Configuration ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# =============================================================================
#  CUSTOM APPLICATION SETTINGS
# =============================================================================
TEMP_TTS_PREVIEWS_DIR_NAME = 'temp_tts_previews'
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

PROFILE_COMPLETION_EXEMPT_URLS = [
    reverse_lazy('AudioXApp:complete_profile'),
    reverse_lazy('account_logout'),
    reverse_lazy('AudioXApp:my_downloads'),
]

ADMIN_URL_PATH = os.getenv('DJANGO_ADMIN_URL', 'admin/')
if not ADMIN_URL_PATH.endswith('/'):
    ADMIN_URL_PATH += '/'

MAX_CREATOR_APPLICATION_ATTEMPTS = int(os.getenv('MAX_CREATOR_APPLICATION_ATTEMPTS', 3))
MIN_CREATOR_WITHDRAWAL_AMOUNT = Decimal(os.getenv('MIN_CREATOR_WITHDRAWAL_AMOUNT', '50.00'))
WITHDRAWAL_REQUEST_COOLDOWN_DAYS = int(os.getenv('WITHDRAWAL_REQUEST_COOLDOWN_DAYS', 15))
DOWNLOAD_DEFAULT_EXPIRY_DAYS = int(os.getenv('DOWNLOAD_DEFAULT_EXPIRY_DAYS', 30))
DOWNLOAD_PREMIUM_EXPIRY_DAYS = int(os.getenv('DOWNLOAD_PREMIUM_EXPIRY_DAYS', 30))
PLATFORM_FEE_PERCENTAGE_AUDIOBOOK = Decimal(os.getenv('PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00'))

SUBSCRIPTION_PRICES = {
    'monthly': os.getenv('MONTHLY_SUB_PRICE', '350.00'),
    'annual': os.getenv('ANNUAL_SUB_PRICE', '3500.00'),
}
SUBSCRIPTION_DURATIONS = {
    'monthly': int(os.getenv('MONTHLY_SUB_DURATION_DAYS', 30)),
    'annual': int(os.getenv('ANNUAL_SUB_DURATION_DAYS', 365)),
}
COIN_PACK_PRICES = {
    '250': os.getenv('COIN_PACK_250_PRICE', '250.00'),
    '500': os.getenv('COIN_PACK_500_PRICE', '500.00'),
    '1000': os.getenv('COIN_PACK_1000_PRICE', '1000.00'),
}

# =============================================================================
#  LOGGING CONFIGURATION
# =============================================================================
# This should generally be one of the last things configured.
LOGGING_CONFIG = None
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] :: %(message)s",
            'datefmt': "%Y-%m-%d %H:%M:%S"
        },
        'simple': {'format': '%(levelname)s %(message)s'},
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
    },
    'loggers': {
        # Configure logging levels for Django and third-party apps
        'django': {'handlers': ['console'], 'propagate': True, 'level': 'INFO'},
        'django.request': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'allauth': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'stripe': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'channels': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'celery': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        # Configure logging for your custom app
        'AudioXApp': {'handlers': ['console'], 'level': 'DEBUG' if DEBUG else 'INFO', 'propagate': False},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO'
    }
})

# Final check for missing AI keys in debug mode
if not GEMINI_API_KEY and DEBUG:
    logging.warning("Warning (DEBUG): GEMINI_API_KEY is not set. AI features will be unavailable.")

