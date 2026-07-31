import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent.parent

load_dotenv(REPO_ROOT / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "apps.accounts",
    "apps.pharmacies",
    "apps.medicines",
    "apps.inventory",
    "apps.imports",
    "apps.customers",
    "apps.sales",
    "apps.prescriptions",
    "apps.eprescriptions",
    "apps.orders",
    "apps.delivery",
    "apps.analytics",
    "apps.integrations",
    "apps.audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.getenv("DJANGO_TEST_SQLITE") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.sqlite3",
            "OPTIONS": {
                # SQLite's default deferred transactions can deadlock when two
                # requests both read and then write (for example, concurrent
                # prescription lookups recording access logs). Acquire the
                # write reservation up front and wait briefly for other
                # short-lived writers instead.
                "transaction_mode": "IMMEDIATE",
                "timeout": 20,
            },
        }
    }
else:
    DATABASES = {
        "default": dj_database_url.parse(
            os.getenv("DATABASE_URL", "postgresql://medisync:medisync@localhost:55432/medisync"),
            conn_max_age=600,
        )
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Beirut"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/private-media/"
PRIVATE_MEDIA_ROOT = BASE_DIR / "media" / "private"
MEDIA_ROOT = PRIVATE_MEDIA_ROOT
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_RATES": {
        # Public prescription endpoints are unauthenticated by design, so they are rate
        # limited per client on top of the per-prescription lockout.
        "rx_lookup": os.getenv("THROTTLE_RX_LOOKUP", "30/min"),
        "rx_dispense": os.getenv("THROTTLE_RX_DISPENSE", "12/min"),
        "public_search": os.getenv("THROTTLE_PUBLIC_SEARCH", "60/min"),
    },
}

CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "false").lower() == "true"

MAX_PRESCRIPTION_FILE_SIZE_MB = int(os.getenv("MAX_PRESCRIPTION_FILE_SIZE_MB", "10"))
MAX_IMPORT_FILE_SIZE_MB = int(os.getenv("MAX_IMPORT_FILE_SIZE_MB", "5"))
DATA_UPLOAD_MAX_MEMORY_SIZE = max(MAX_PRESCRIPTION_FILE_SIZE_MB, MAX_IMPORT_FILE_SIZE_MB) * 1024 * 1024

# Public web app, used to build the URL embedded in prescription QR codes.
PUBLIC_WEB_BASE_URL = os.getenv("PUBLIC_WEB_BASE_URL", "http://localhost:3000")

# --- E-prescriptions -------------------------------------------------------------------
PRESCRIPTION_VALIDITY_DAYS = int(os.getenv("PRESCRIPTION_VALIDITY_DAYS", "30"))
PRESCRIPTION_MAX_FAILED_ATTEMPTS = int(os.getenv("PRESCRIPTION_MAX_FAILED_ATTEMPTS", "5"))
PRESCRIPTION_LOCKOUT_MINUTES = int(os.getenv("PRESCRIPTION_LOCKOUT_MINUTES", "15"))

# --- Consumer marketplace --------------------------------------------------------------
# Pharmacies never expose true stock depth publicly. Shoppers see and order up to this many
# units of an item from one pharmacy at a time (a per-pharmacy override exists).
PUBLIC_MAX_QUANTITY_PER_ITEM = int(os.getenv("PUBLIC_MAX_QUANTITY_PER_ITEM", "10"))
MAX_SOURCING_RADIUS_KM = float(os.getenv("MAX_SOURCING_RADIUS_KM", "12"))
MAX_ORDER_SCHEDULE_DAYS = int(os.getenv("MAX_ORDER_SCHEDULE_DAYS", "30"))
STOCK_RESERVATION_MINUTES = int(os.getenv("STOCK_RESERVATION_MINUTES", "120"))
DELIVERY_BASE_FEE = os.getenv("DELIVERY_BASE_FEE", "3.00")
ASAP_DELIVERY_PROMISE_MINUTES = int(os.getenv("ASAP_DELIVERY_PROMISE_MINUTES", "120"))

# --- Email -----------------------------------------------------------------------------
# The console backend prints prescription emails (QR included) to the server log, so the POC
# needs no SMTP account. Point EMAIL_* at a real host and nothing else changes.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "MediSync <no-reply@medisync.test>")
