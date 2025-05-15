# AudioXCore/settings.py

from pathlib import Path
import os
from dotenv import load_dotenv
import logging # Keep this
import logging.config # Keep this
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
from decimal import Decimal # Required for Stripe price settings

# Basic logging setup (can be configured further below)
# logging.basicConfig(level=logging.INFO, format='{levelname} {asctime} {name} {message}', style='{') # Already configured via dictConfig
logger = logging.getLogger(__name__) # Keep this

BASE_DIR = Path(__file__).resolve().parent.parent
dotenv_path = BASE_DIR / '.env'

if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    logger.warning(f"WARNING: .env file not found at {dotenv_path}.")

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
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'AudioXApp', # Your app

    'django.contrib.humanize',
    'mathfilters',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
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
    'allauth.account.middleware.AccountMiddleware', # Ensure this is after SessionMiddleware and AuthenticationMiddleware
    'AudioXApp.middleware.ProfileCompletionMiddleware',
]

ROOT_URLCONF = 'AudioXCore.urls' # Make sure 'AudioXCore' is your project directory name

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request', # Required by allauth
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'AudioXCore.wsgi.application' # Make sure 'AudioXCore' is your project directory name

# --- Database Configuration ---
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST', '127.0.0.1' if DEBUG else None)
DB_PORT = os.getenv('DB_PORT', '5432' if DEBUG else None)
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'public') # Default to 'public' if not set

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
TIME_ZONE = 'Asia/Karachi' # Your specified timezone
USE_I18N = True
USE_TZ = True # Important for timezone-aware datetimes

# --- Static files ---
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_collected') # For production
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'), # For development
]
# For whitenoise, ensure this is after security middleware and before sessions
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
os.makedirs(STATIC_ROOT, exist_ok=True) # Ensure directory exists

# --- Media files ---
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
os.makedirs(MEDIA_ROOT, exist_ok=True) # Ensure directory exists

# Setting for temporary TTS preview files directory (relative to MEDIA_ROOT)
TEMP_TTS_PREVIEWS_DIR_NAME = 'temp_tts_previews'

# --- Default primary key ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Custom User Model ---
AUTH_USER_MODEL = 'AudioXApp.User' # Matches your models.py
LOGIN_URL = '/login/' # Or your actual login URL name: reverse_lazy('AudioXApp:login_view_name')

# --- Email Configuration ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587)) # Default to 587 if not set
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True' # Typically TLS or SSL, not both
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or 'webmaster@localhost' # Fallback for default from email

if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]) and not DEBUG:
    logger.warning("Production Email settings not fully configured. Email features may fail.")
elif not all([EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]) and DEBUG:
    logger.info("Development Email settings not fully configured. Using console backend if issues arise.")
    # EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' # Uncomment to test emails in console

# --- Caching ---
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'audiox-local-cache', # Unique name for this cache
    }
}

# --- Stripe Configuration ---
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Stripe Price IDs from .env
STRIPE_PRICE_ID_COINS_250 = os.getenv('STRIPE_PRICE_ID_COINS_250')
STRIPE_PRICE_ID_COINS_500 = os.getenv('STRIPE_PRICE_ID_COINS_500')
STRIPE_PRICE_ID_COINS_1000 = os.getenv('STRIPE_PRICE_ID_COINS_1000')
STRIPE_PRICE_ID_SUB_MONTHLY = os.getenv('STRIPE_PRICE_ID_SUB_MONTHLY')
STRIPE_PRICE_ID_SUB_ANNUAL = os.getenv('STRIPE_PRICE_ID_SUB_ANNUAL')

# Check critical Stripe settings
if not all([STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY]) and not DEBUG:
    raise ImproperlyConfigured("CRITICAL (PRODUCTION): Stripe keys (publishable or secret) missing.")
if not STRIPE_WEBHOOK_SECRET:
    logger.warning("Stripe Webhook Secret (STRIPE_WEBHOOK_SECRET) is missing in .env. Webhooks will not be secure and might fail signature verification.")
if not all([STRIPE_PRICE_ID_COINS_250, STRIPE_PRICE_ID_COINS_500, STRIPE_PRICE_ID_COINS_1000, STRIPE_PRICE_ID_SUB_MONTHLY, STRIPE_PRICE_ID_SUB_ANNUAL]):
    logger.warning("One or more Stripe Price IDs are missing from .env. Purchases might fail.")

# --- ADD THESE DICTIONARIES FOR WEBHOOK LOGIC ---
# These are used by your webhook to determine default prices/durations if not directly available from Stripe event
# or for logging purposes. Values are loaded from .env with fallbacks.
SUBSCRIPTION_PRICES = {
    'monthly': os.getenv('MONTHLY_SUB_PRICE', '350.00'), # Fallback price
    'annual': os.getenv('ANNUAL_SUB_PRICE', '3500.00'),  # Fallback price
}

SUBSCRIPTION_DURATIONS = { # in days
    'monthly': int(os.getenv('MONTHLY_SUB_DURATION_DAYS', 30)), # Fallback duration
    'annual': int(os.getenv('ANNUAL_SUB_DURATION_DAYS', 365)), # Fallback duration
}

COIN_PACK_PRICES = { # Prices for coin packs, keys should match item_id from metadata
    '250': os.getenv('COIN_PACK_250_PRICE', '250.00'), # Fallback price
    '500': os.getenv('COIN_PACK_500_PRICE', '500.00'), # Fallback price
    '1000': os.getenv('COIN_PACK_1000_PRICE', '1000.00'), # Fallback price
}

PLATFORM_FEE_PERCENTAGE_AUDIOBOOK = os.getenv('PLATFORM_FEE_PERCENTAGE_AUDIOBOOK', '10.00') # Fallback fee
# --- END OF ADDITIONS ---


# --- Django Allauth Configuration (Updated) ---
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',        # Default Django auth
    'allauth.account.auth_backends.AuthenticationBackend', # Allauth specific
]

SITE_ID = 1 # Required by allauth

# Defines how users log in. Using 'email' means users will log in with their email address.
# This replaces the deprecated ACCOUNT_AUTHENTICATION_METHOD.
ACCOUNT_LOGIN_METHODS = ('email',) # Changed from ACCOUNT_AUTHENTICATION_METHOD = 'email'

# Ensures that email addresses are unique across all accounts.
ACCOUNT_UNIQUE_EMAIL = True

# Determines if and how email verification is handled.
# 'none': No verification email sent. User is active immediately.
# 'optional': Verification email sent, but user can log in without verifying.
# 'mandatory': Verification email sent, user must verify before logging in.
ACCOUNT_EMAIL_VERIFICATION = 'none' # Change as per your requirements

# The following settings are deprecated and have been removed or their behavior
# is now controlled by other settings or defaults:
# ACCOUNT_AUTHENTICATION_METHOD = 'email' # Replaced by ACCOUNT_LOGIN_METHODS
# ACCOUNT_EMAIL_REQUIRED = True # Email is implicitly required if 'email' is in ACCOUNT_LOGIN_METHODS.
# ACCOUNT_USERNAME_REQUIRED = False # Username requirement is now primarily handled by its presence
                                    # in ACCOUNT_SIGNUP_FIELDS and your User model definition.
# ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = True # This is default behavior for signup forms.

# Specifies additional fields to be collected during user signup.
# 'email' (as defined in ACCOUNT_LOGIN_METHODS) and 'password' fields are automatically
# added to the signup form by allauth.
# List any other fields from your custom User model or profile that you want to collect here.
# Your current setting ("full_name", "username") means these will be on the signup form.
ACCOUNT_SIGNUP_FIELDS = ("full_name", "username")


# Optional: Configure login attempt limits to enhance security.
# ACCOUNT_LOGIN_ATTEMPTS_LIMIT = 5
# ACCOUNT_LOGIN_ATTEMPTS_TIMEOUT = 300 # Seconds (e.g., 300 for 5 minutes)

# If True, users signing up via a social account provider will be automatically signed up
# without needing to fill out a signup form (if provider gives enough info).
SOCIALACCOUNT_AUTO_SIGNUP = True
# If True, allows initiating social login via a GET request. Useful for simple links.
SOCIALACCOUNT_LOGIN_ON_GET = True

# If you have a custom signup form (e.g., inheriting from allauth.account.forms.SignupForm),
# specify its Python path here.
# ACCOUNT_SIGNUP_FORM_CLASS = 'AudioXApp.forms.CustomSignupForm'

# Default adapter classes. You have a custom social account adapter.
ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'AudioXApp.adapters.CustomSocialAccountAdapter'

# URL to redirect to after a successful login.
LOGIN_REDIRECT_URL = reverse_lazy('AudioXApp:home')
# URL to redirect to after a successful logout.
LOGOUT_REDIRECT_URL = reverse_lazy('AudioXApp:home')

# Configuration for social account providers (e.g., Google).
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        # Specifies the OAuth scopes to request from Google.
        'SCOPE': [
            'profile', # Access basic profile information.
            'email',   # Access user's email address.
        ],
        # Additional authentication parameters for Google.
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        # Application credentials from Google Developer Console.
        # These should be stored securely, typically in environment variables.
        'APP': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'key': '' # Typically not used for Google OAuth2.
        },
        # If True, only allows signups from Google accounts with verified email addresses.
        'VERIFIED_EMAIL': True,
    }
}
# --- End Django Allauth Configuration ---


# --- Logging Configuration (using dictConfig) ---
LOGGING_CONFIG = None # Disable Django's default logging config
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt': "%d/%b/%Y %H:%M:%S"
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
        # Optional: Add a file handler for production
        # 'file': {
        #     'level': 'INFO',
        #     'class': 'logging.handlers.RotatingFileHandler',
        #     'filename': BASE_DIR / 'logs/django.log',
        #     'maxBytes': 1024*1024*5, # 5 MB
        #     'backupCount': 5,
        #     'formatter': 'verbose',
        # },
    },
    'loggers': {
        'django': {
            'handlers': ['console'], # Add 'file' here if using file handler
            'propagate': True,
            'level': 'INFO',
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING', # Reduce noise from successful requests
            'propagate': False,
        },
        'AudioXApp': { # Your app's logger
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False, # Don't pass to root logger if handled here
        },
        'allauth': {
            'handlers': ['console'],
            'level': 'INFO', # Or DEBUG if troubleshooting allauth
            'propagate': False,
        },
        'stripe': { # Stripe library's own logger
            'handlers': ['console'],
            'level': 'INFO', # Or WARNING to reduce verbosity
            'propagate': False,
        }
    },
    'root': { # Catch-all for other loggers
        'handlers': ['console'],
        'level': 'INFO',
    }
})
# --- End Logging Configuration ---

# Custom setting for ProfileCompletionMiddleware
PROFILE_COMPLETION_EXEMPT_URLS = [
    reverse_lazy('AudioXApp:complete_profile'),
    reverse_lazy('account_logout'),
    # Add other URLs that should be exempt, like password reset, etc.
    # reverse_lazy('account_reset_password'),
]
# Add admin URLs to exempt paths for the middleware
ADMIN_URL_PATH = os.getenv('DJANGO_ADMIN_URL', 'admin/') # Get admin URL from .env or default to 'admin/'
if not ADMIN_URL_PATH.endswith('/'):
    ADMIN_URL_PATH += '/'
PROFILE_COMPLETION_EXEMPT_URLS.append(reverse_lazy('admin:index')) # More robust way to get admin index


# Ensure Stripe API key is set for the stripe library
if STRIPE_SECRET_KEY:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("Stripe API secret key is not set. Stripe API calls will fail.")

# Creator Application Settings
MAX_CREATOR_APPLICATION_ATTEMPTS = int(os.getenv('MAX_CREATOR_APPLICATION_ATTEMPTS', 3))
WITHDRAWAL_REQUEST_COOLDOWN_DAYS = int(os.getenv('WITHDRAWAL_REQUEST_COOLDOWN_DAYS', 15))

