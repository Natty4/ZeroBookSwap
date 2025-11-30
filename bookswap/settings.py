import os 
import dotenv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


dotenv.load_dotenv()


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", '')


DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # Third party apps
    'rest_framework',
    'corsheaders',
    
    # Local apps
    'core',
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    'whitenoise.middleware.WhiteNoiseMiddleware',
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bookswap.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bookswap.wsgi.application"




DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]




LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Addis_Ababa"

USE_I18N = True

USE_TZ = True



STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

if not DEBUG:
    # Production settings
    CORS_ALLOWED_ORIGINS = [
        "https://frontxt.app",
        "https://zero-com.netlify.app",
    ]
    CSRF_TRUSTED_ORIGINS = [
        "https://frontxt.app", 
        "https://zero-com.netlify.app",
        "https://zerobookswap.onrender.com",
    ]
    
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SAMESITE = 'None'  # Required for cross-site
    CSRF_COOKIE_SAMESITE = 'None'     # Required for cross-site
    SESSION_COOKIE_SECURE = True      # Required for SameSite=None
    CSRF_COOKIE_SECURE = True         # Required for SameSite=None
    CSRF_COOKIE_HTTPONLY = False      # Allow JavaScript to read CSRF token
    SESSION_COOKIE_DOMAIN = None
    CSRF_COOKIE_DOMAIN = None
    
else:
    # Development settings
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:3000",
    ]
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:8001",
        "http://127.0.0.1:8001", 
        "http://localhost:3000",
    ]
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_DOMAIN = None
    CSRF_COOKIE_DOMAIN = None
    
# Custom settings
ZCOIN_PRICE_PER_BIRR = os.getenv('ZCOIN_PRICE_PER_BIRR', 100)
SWAP_FEE = os.getenv('SWAP_FEE', 25)