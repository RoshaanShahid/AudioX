from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'your-secret-key')
DEBUG = os.getenv('DJANGO_DEBUG', 'True') == 'True'

# Allowed Hosts
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'yourdomain.com'] # Add any other hosts if needed

# Installed Apps
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'AudioXApp', # Your app
]

# Middleware
MIDDLEWARE = [
    # Note: WhiteNoiseMiddleware should typically come after SecurityMiddleware
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # For serving static files efficiently
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URL Configuration
ROOT_URLCONF = 'AudioXCore.urls' # Make sure this matches your project name

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # Central templates directory
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

# WSGI Application
WSGI_APPLICATION = 'AudioXCore.wsgi.application' # Make sure this matches your project name

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'audix_db'),
        'USER': os.getenv('DB_USER', 'audiox_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'hello123'),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'options': '-c search_path=audiox_schema,public', # Ensure schema exists
        },
    }
}

# Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    # Add other validators if needed
    # { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    # { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True # Important for timezone-aware datetimes

# Static Files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
# This is where collectstatic will gather files for deployment
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Directories where Django looks for static files in addition to app static/ dirs
# Only add STATICFILES_DIRS if the static directory exists at the project root
if os.path.exists(os.path.join(BASE_DIR, 'static')):
    STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Simplified static file serving for development (handled by WhiteNoise in production)
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage' # Use for production

# Media Files (User Uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'AudioXApp.User' # Make sure app name and model name are correct

# Login URL (Where @login_required redirects)
LOGIN_URL = '/login/' # Ensure this URL exists in your urls.py

EMAIL_HOST_USER = 'iam.burhanaqeel@gmail.com'  # Your Gmail address
EMAIL_HOST_PASSWORD = 'tdtpydselbzdcpkd'  # The 16-character App Password
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True


# --- Added Cache Configuration ---
CACHES = {
    'default': {
        # Using local memory cache for development. Fast and simple.
        # Data is lost when the server restarts.
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        # Location name can be anything unique if needed, often not critical for locmem
        'LOCATION': 'audiox-local-cache',

        # --- Example for Production using Redis (Requires django-redis) ---
        # pip install django-redis
        # 'BACKEND': 'django_redis.cache.RedisCache',
        # 'LOCATION': os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1'), # Use env var for Redis URL
        # 'OPTIONS': {
        #     'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        # }
        # --- Example for Production using Memcached (Requires python-memcached or pylibmc) ---
        # pip install python-memcached
        # 'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache', # Or PyLibMCCache
        # 'LOCATION': '127.0.0.1:11211', # Your Memcached server(s)
    }
}

# Session Engine (Optional: Use cached sessions for better performance)
# SESSION_ENGINE = "django.contrib.sessions.backends.cache"
# SESSION_CACHE_ALIAS = "default"

