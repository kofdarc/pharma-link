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
    "storages",
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
    "apps.payments",
    "apps.billing",
    "apps.insurance",
    "apps.delivery",
    "apps.analytics",
    "apps.integrations",
    "apps.audit",
    "apps.messaging",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
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
            os.getenv("DATABASE_URL", "postgresql://pharmalink:pharmalink@localhost:55432/pharmalink"),
            conn_max_age=600,
        )
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Beirut"
USE_I18N = True
USE_TZ = True

# Lebanon is Arabic/French/English. LocaleMiddleware (below) picks the active language from
# the request's Accept-Language header, so the frontend just needs to send the language the
# shopper picked - no per-endpoint language parameter. Translated strings live in locale/
# (apps/api/locale/<lang>/LC_MESSAGES/django.po), generated with `manage.py makemessages`.
LANGUAGES = [
    ("en", "English"),
    ("ar", "Arabic"),
    ("fr", "French"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/private-media/"
PRIVATE_MEDIA_ROOT = BASE_DIR / "media" / "private"
MEDIA_ROOT = PRIVATE_MEDIA_ROOT

# Product photography (medicine/supplement images) is not sensitive like prescriptions, so it
# lives in its own public root/URL instead of the private prescription storage above.
PUBLIC_MEDIA_URL = "/media/"
PUBLIC_MEDIA_ROOT = BASE_DIR / "media" / "public"
# Development can read public product photography directly from a remote bucket while
# keeping ImageField values storage-relative (for example, medicines/<uuid>.webp).
# Production ignores this and uses ProductImageStorage's S3 backend when USE_S3=true.
PRODUCT_IMAGE_BASE_URL = os.getenv("PRODUCT_IMAGE_BASE_URL", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Prescription file storage ----------------------------------------------------------
# Local disk in development. In production, point this at S3 (see docs/DEPLOY_AWS.md) so
# scanned prescriptions survive redeploys - App Runner's container filesystem is ephemeral.
# Files stay encrypted at the application layer either way (see apps/prescriptions/storage.py).
USE_S3 = os.getenv("USE_S3", "false").lower() == "true"
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or None
AWS_S3_ADDRESSING_STYLE = "virtual"
# The bucket should have ACLs disabled (Object Ownership: "Bucket owner enforced", the AWS
# default for new buckets) with access controlled entirely by bucket policy/IAM - so no
# per-object ACL is sent.
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = False
if os.getenv("AWS_ACCESS_KEY_ID"):
    # Only needed for local testing against S3. On App Runner, leave these unset and grant
    # the App Runner instance role S3 access instead - boto3 picks up credentials from the
    # role automatically.
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

AUTH_TOKEN_TTL_HOURS = int(os.getenv("AUTH_TOKEN_TTL_HOURS", "24"))

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ExpiringTokenAuthentication",
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
        # Per-client cap on login attempts, on top of Django's own password validation.
        "login": os.getenv("THROTTLE_LOGIN", "10/min"),
        # Password reset / email verification request+confirm endpoints - unauthenticated by
        # design, so capped per client to slow down account enumeration and token guessing.
        "account_recovery": os.getenv("THROTTLE_ACCOUNT_RECOVERY", "10/min"),
        # Machine API (apps.integrations): scoped per integration key's pharmacy, not IP -
        # see apps.integrations.throttling.IntegrationKeyThrottle.
        "integration_api": os.getenv("THROTTLE_INTEGRATION_API", "120/min"),
    },
}

CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "false").lower() == "true"

# App Runner (and most managed AWS load balancers) terminate TLS upstream and forward plain
# HTTP with this header - without it, Django can't tell the request was actually HTTPS and
# SECURE_SSL_REDIRECT would redirect-loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

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
# Single source of truth for the currency every price/payment is denominated in. Not
# multi-currency support - Lebanon's dual-currency (USD/LBP) reality is out of scope here,
# this just stops "USD" from being a silently repeated literal across the codebase.
PLATFORM_CURRENCY = os.getenv("PLATFORM_CURRENCY", "USD")
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
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "HealthConnect <no-reply@pharmalink.test>")

# --- Prescription OCR -------------------------------------------------------------------
# Self-hosted Tesseract is the default so OCR intake needs no external account - it handles
# printed prescriptions well but poorly on doctor handwriting (docs/AI_FEATURES.md §2).
# PRESCRIPTION_OCR_PROVIDER="easyocr" is a free, still self-hosted step up (a real
# detection+recognition model instead of classical glyph matching) at the cost of a much
# heavier dependency (PyTorch) and slower requests - see apps.prescriptions.services.ocr.
# PRESCRIPTION_OCR_PROVIDER="anthropic" (+ ANTHROPIC_API_KEY) reads handwriting far better
# than either free option, since it's a real vision-language model with drug-name world
# knowledge - but that path sends the prescription image (which can carry patient/doctor
# names) to Anthropic's API: don't switch it on without checking your data-handling/
# compliance posture first.
PRESCRIPTION_OCR_PROVIDER = os.getenv("PRESCRIPTION_OCR_PROVIDER", "tesseract")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_OCR_MODEL = os.getenv("ANTHROPIC_OCR_MODEL", "claude-sonnet-5")

# --- WhatsApp ----------------------------------------------------------------------------
# The console provider logs messages instead of calling Meta's API, so dev/test needs no
# WhatsApp Business account. Point WHATSAPP_PROVIDER at "meta_cloud" and supply the token/
# phone-number-id to send real messages (see apps.messaging.providers.meta_cloud).
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "console")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")  # signs inbound webhook payloads (X-Hub-Signature-256)

# --- Prescription fax back-up -------------------------------------------------------------
# PrescribeIT-style guaranteed delivery: when a prescription can't be emailed to the patient
# (no address on file, or the send fails), it's faxed instead. Console logs instead of
# calling a real fax gateway (see apps.eprescriptions.services.fax).
FAX_PROVIDER = os.getenv("FAX_PROVIDER", "console")
