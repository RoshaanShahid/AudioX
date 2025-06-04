# AudioXCore/settings.py

from pathlib import Path
import os
from dotenv import load_dotenv
import logging
import logging.config
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy # Make sure reverse_lazy is imported
from decimal import Decimal

# Basic logging setup (configured further below)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / '.env'

if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    logger.warning(f"WARNING: .env file not found at {dotenv_path}.")

# --- Core Django Settings ---
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'

if not SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): DJANGO_SECRET_KEY not set.")
elif not SECRET_KEY and DEBUG:
    logger.warning("Warning (DEBUG): DJANGO_SECRET_KEY not set. Using insecure dummy key.")
    SECRET_KEY = 'django-insecure-dummy-key-for-debug-set-a-real-one-in-env'

ALLOWED_HOSTS_STRING = os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost' if DEBUG else None)
if not ALLOWED_HOSTS_STRING and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): DJANGO_ALLOWED_HOSTS not set.")

ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',') if host.strip()] if ALLOWED_HOSTS_STRING else []
if DEBUG:
    ALLOWED_HOSTS.extend(['127.0.0.1', 'localhost'])
    ALLOWED_HOSTS = list(set(ALLOWED_HOSTS)) # Ensure uniqueness

INSTALLED_APPS = [
    'daphne',
    'channels',  # For Django Channels
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # --- RESOLVED CONFLICT 1 HERE ---
    'AudioXApp', # Your application 
    # --- END RESOLVED CONFLICT 1 ---

    'django.contrib.humanize',
    'mathfilters',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    'rest_framework', # Added by friend
    'rest_framework.authtoken', # Added by friend (likely with rest_framework)
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Whitenoise for static files
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware', # Django Allauth
    'AudioXApp.middleware.ProfileCompletionMiddleware', # Your custom middleware
]

ROOT_URLCONF = 'AudioXCore.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # Project-level templates
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
ASGI_APPLICATION = 'AudioXCore.asgi.application' # Tells Django to use your ASGI config for Channels

# --- Database Configuration ---
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', '127.0.0.1' if DEBUG else None)
DB_PORT = os.getenv('DB_PORT', '5432' if DEBUG else None) # Default PostgreSQL port
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'public') # For PostgreSQL schemas

if not all([DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT]) and not DEBUG:
    logger.warning("Production Database connection details might be missing or incomplete.")

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
if DB_ENGINE == 'django.db.backends.postgresql' and DB_SCHEMA and DB_SCHEMA.lower() != 'public':
    DATABASES['default'].setdefault('OPTIONS', {})['options'] = f'-c search_path={DB_SCHEMA},public'

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

# --- Static files (CSS, JavaScript, Images) ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_collected')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
os.makedirs(STATIC_ROOT, exist_ok=True)

# --- Media files (User-uploaded content) ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
os.makedirs(MEDIA_ROOT, exist_ok=True)

TEMP_TTS_PREVIEWS_DIR_NAME = 'temp_tts_previews'

# --- Default primary key type ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Custom User Model ---
AUTH_USER_MODEL = 'AudioXApp.User'
LOGIN_URL = reverse_lazy('account_login') # Using allauth's typical login URL name

# --- Django Messages Framework ---
# Forcing SessionStorage for messages to debug persistence issues
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

# --- Email Configuration ---
EMAIL_BACKEND = os.getenv('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'webmaster@localhost')

if EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend':
    if not all([EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]) and not DEBUG:
        logger.warning("Production Email (SMTP) settings not fully configured. Email features may fail.")
    elif not all([EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]) and DEBUG:
        logger.info("Development Email (SMTP) settings not fully configured. Using console backend if issues arise with SMTP.")
elif DEBUG and EMAIL_BACKEND != 'django.core.mail.backends.console.EmailBackend':
    logger.info(f"Email backend is set to {EMAIL_BACKEND}. For development, consider 'django.core.mail.backends.console.EmailBackend'.")

# --- Caching ---
CACHE_LOCATION_PATH = os.path.join(BASE_DIR, 'django_cache_data')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': CACHE_LOCATION_PATH,
        'TIMEOUT': 3600,
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}
try:
    os.makedirs(CACHE_LOCATION_PATH, exist_ok=True)
    logger.info(f"DJANGO CACHE: Using FileBasedCache. Location: {CACHE_LOCATION_PATH}")
except OSError as e:
    logger.error(f"DJANGO CACHE: Could not create/access cache directory {CACHE_LOCATION_PATH}: {e}")

# --- Channel Layers Configuration ---
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer', # Suitable for development
        # For production, consider 'channels_redis.core.RedisChannelLayer'
        # 'CONFIG': {
        #     "hosts": [(os.getenv('REDIS_HOST', '127.0.0.1'), os.getenv('REDIS_PORT', 6379))],
        # },
    },
}

# --- Stripe Configuration ---
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

STRIPE_PRICE_ID_COINS_250 = os.getenv('STRIPE_PRICE_ID_COINS_250')
STRIPE_PRICE_ID_COINS_500 = os.getenv('STRIPE_PRICE_ID_COINS_500')
STRIPE_PRICE_ID_COINS_1000 = os.getenv('STRIPE_PRICE_ID_COINS_1000')
STRIPE_PRICE_ID_SUB_MONTHLY = os.getenv('STRIPE_PRICE_ID_SUB_MONTHLY')
STRIPE_PRICE_ID_SUB_ANNUAL = os.getenv('STRIPE_PRICE_ID_SUB_ANNUAL')

if not all([STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY]) and not DEBUG:
    logger.warning("Production Stripe keys (publishable or secret) might be missing.")
if not STRIPE_WEBHOOK_SECRET and not DEBUG:
    logger.warning("Production Stripe Webhook Secret (STRIPE_WEBHOOK_SECRET) is missing. Webhooks will not be secure.")
if not all([STRIPE_PRICE_ID_COINS_250, STRIPE_PRICE_ID_COINS_500, STRIPE_PRICE_ID_COINS_1000, STRIPE_PRICE_ID_SUB_MONTHLY, STRIPE_PRICE_ID_SUB_ANNUAL]):
    logger.warning("One or more Stripe Price IDs are missing from .env. Purchases might fail.")

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
PLATFORM_FEE_PERCENTAGE_AUDIOBOOK = os.getenv('PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00')

if STRIPE_SECRET_KEY:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("Stripe API secret key is not set. Stripe API calls will fail.")

# --- Django Allauth Configuration ---
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1

# --- RESOLVED CONFLICT 2 HERE ---
ACCOUNT_AUTHENTICATION_METHOD = 'email' 
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False # From HEAD: Set to False if email is primary identifier
ACCOUNT_EMAIL_VERIFICATION = os.getenv('ACCOUNT_EMAIL_VERIFICATION', 'none') # From HEAD (configurable)
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = True # From HEAD: This is still a valid setting
ACCOUNT_SESSION_REMEMBER = True # From HEAD
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True # From HEAD
ACCOUNT_SIGNUP_FIELDS = ("full_name", "username") # From friend
SOCIALACCOUNT_AUTO_SIGNUP = True # From friend
# --- END RESOLVED CONFLICT 2 ---
SOCIALACCOUNT_LOGIN_ON_GET = True 
ACCOUNT_LOGOUT_ON_GET = True 

ACCOUNT_ADAPTER = 'AudioXApp.adapters.CustomAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'AudioXApp.adapters.CustomSocialAccountAdapter'

LOGIN_REDIRECT_URL = reverse_lazy('AudioXApp:home')
LOGOUT_REDIRECT_URL = reverse_lazy('AudioXApp:home') 

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'APP': { 
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'key': '' 
        },
        # --- RESOLVED PART OF CONFLICT 3 (VERIFIED_EMAIL comment) ---
        'VERIFIED_EMAIL': True, # Usually default, good to be explicit (using HEAD's comment)
        # --- END RESOLVED PART OF CONFLICT 3 ---
    }
}

# --- RESOLVED CONFLICT 3 (REST_FRAMEWORK block) ---
# --- Django REST Framework Configuration (from friend's changes) ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated', # Default to authenticated for APIs
    ],
    # 'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    # 'PAGE_SIZE': 10,
}
# --- END Django REST Framework Configuration ---
# --- END RESOLVED CONFLICT 3 ---

# --- Logging Configuration (dictConfig) ---
LOGGING_CONFIG = None 
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(module)s %(process)d %(thread)d :: %(message)s",
            'datefmt': "%Y-%m-%d %H:%M:%S"
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO', 
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
        # 'file': {
        #     'level': 'INFO',
        #     'class': 'logging.FileHandler',
        #     'filename': BASE_DIR / 'logs/django.log',
        #     'formatter': 'verbose',
        # },
    },
    'loggers': {
        'django': {
            'handlers': ['console'], 
            'propagate': True,
            'level': 'INFO', 
        },
        'django.request': { 
            'handlers': ['console'],
            # --- RESOLVED CONFLICT 4 HERE ---
            'level': 'WARNING', # Changed from ERROR to WARNING to see more request issues (using HEAD's comment)
            # --- END RESOLVED CONFLICT 4 ---
            'propagate': False,
        },
        'AudioXApp': { 
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False, 
        },
        'allauth': {
            'handlers': ['console'],
            'level': 'INFO', 
            'propagate': False,
        },
        'stripe': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # --- RESOLVED CONFLICT 5 HERE ---
        'channels': { # From HEAD
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'rest_framework': { # From friend
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Add other specific app loggers here if needed (comment from friend)
        # --- END RESOLVED CONFLICT 5 ---
    },
    'root': { 
        'handlers': ['console'],
        'level': 'INFO', 
    }
})

# --- Custom Application Settings (AudioXApp specific) ---
PROFILE_COMPLETION_EXEMPT_URLS = [
    reverse_lazy('AudioXApp:complete_profile'),
    reverse_lazy('account_logout'), 
    reverse_lazy('AudioXApp:my_downloads'), 
]
ADMIN_URL_PATH = os.getenv('DJANGO_ADMIN_URL', 'admin/') 
if not ADMIN_URL_PATH.endswith('/'):
    ADMIN_URL_PATH += '/'
# --- RESOLVED CONFLICT 6 HERE ---
# try: # Commented block from friend
# PROFILE_COMPLETION_EXEMPT_URLS.append(reverse_lazy('admin:index'))
# except Exception:
# logger.warning("Could not add admin:index to PROFILE_COMPLETION_EXEMPT_URLS. Ensure admin path is handled if needed.")
# --- END RESOLVED CONFLICT 6 ---

MAX_CREATOR_APPLICATION_ATTEMPTS = int(os.getenv('MAX_CREATOR_APPLICATION_ATTEMPTS', 3))
MIN_CREATOR_WITHDRAWAL_AMOUNT = Decimal(os.getenv('MIN_CREATOR_WITHDRAWAL_AMOUNT', '50.00'))
WITHDRAWAL_REQUEST_COOLDOWN_DAYS = int(os.getenv('WITHDRAWAL_REQUEST_COOLDOWN_DAYS', 15))
# MIN_CREATOR_WITHDRAWAL_AMOUNT = Decimal(os.getenv('MIN_CREATOR_WITHDRAWAL_AMOUNT', '50.00')) # This line is duplicated, removing one

# Download Feature Settings (Optional)
DOWNLOAD_DEFAULT_EXPIRY_DAYS = int(os.getenv('DOWNLOAD_DEFAULT_EXPIRY_DAYS', 30)) 
DOWNLOAD_PREMIUM_EXPIRY_DAYS = int(os.getenv('DOWNLOAD_PREMIUM_EXPIRY_DAYS', 30)) 
# --- END Custom Settings ---

# --- Google Gemini AI Configuration ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- RESOLVED CONFLICT 7 HERE ---
if not GEMINI_API_KEY and not DEBUG: # More robust warning from friend
    logger.critical("CRITICAL (PRODUCTION): GEMINI_API_KEY is not set in .env. AI features will fail.")
elif not GEMINI_API_KEY and DEBUG:
    logger.warning("Warning (DEBUG): GEMINI_API_KEY is not set in .env. AI features will be unavailable.")

# --- DeepSeek AI Configuration (from friend) ---
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')

if not DEEPSEEK_API_KEY and not DEBUG:
    logger.critical("CRITICAL (PRODUCTION): DEEPSEEK_API_KEY is not set in .env. AI summary features will fail.")
elif not DEEPSEEK_API_KEY and DEBUG:
    logger.warning("Warning (DEBUG): DEEPSEEK_API_KEY is not set in .env. AI summary features will be unavailable.")
# --- END RESOLVED CONFLICT 7 ---