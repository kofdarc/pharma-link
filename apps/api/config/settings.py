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
    "apps.assistant",
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
        # The in-app assistant is open to anonymous visitors on the public pages, so it is
        # capped per client. Generous enough for a real conversation, tight enough that
        # scripting it into a free classifier for somebody else's workload is not worth it.
        "assistant": os.getenv("THROTTLE_ASSISTANT", "20/min"),
        # Narrative digest (apps.analytics.services.narrative): each call to a configured
        # ANALYTICS_AI_PROVIDER costs real money and hits an external API, unlike every other
        # analytics endpoint (all pure DB reads) - capped low since one pharmacy owner has no
        # reason to regenerate it more than a handful of times a day.
        "analytics_digest": os.getenv("THROTTLE_ANALYTICS_DIGEST", "20/day"),
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
# Smallest side (px) an uploaded scan may have before the legibility gate refuses it
# (apps.prescriptions.services.quality). 200 is permissive - real phone photos clear it by
# an order of magnitude; raise it if too many unusable thumbnails get through, lower it to
# accept screenshots/crops.
PRESCRIPTION_MIN_SCAN_DIMENSION = int(os.getenv("PRESCRIPTION_MIN_SCAN_DIMENSION", "200"))
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
# needs no SMTP account. Point EMAIL_* at a real host and nothing else changes, OR set
# EMAIL_BACKEND="apps.common.email_backends.SESEmailBackend" to send through AWS SES (no SMTP
# credentials - boto3 uses the environment / task-role credentials, and AWS_SES_REGION_NAME
# selects the region). The SES sender identity must be verified; see docs/DEPLOY_AWS.md.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "HealthConnect <no-reply@healthconnect.dev>")
AWS_SES_REGION_NAME = os.getenv("AWS_SES_REGION_NAME", "eu-central-1")
# Optional SES configuration set (open/click/bounce event publishing); blank = don't send one.
SES_CONFIGURATION_SET = os.getenv("SES_CONFIGURATION_SET", "")

# --- Prescription OCR -------------------------------------------------------------------
# Self-hosted Tesseract is the default so OCR intake needs no external account - it handles
# printed prescriptions well but poorly on doctor handwriting (docs/AI_FEATURES.md §2).
# PRESCRIPTION_OCR_PROVIDER="easyocr" is a free, still self-hosted step up (a real
# detection+recognition model instead of classical glyph matching) at the cost of a much
# heavier dependency (PyTorch) and slower requests - see apps.prescriptions.services.ocr.
# PRESCRIPTION_OCR_PROVIDER="anthropic" (+ ANTHROPIC_API_KEY) reads handwriting far better
# than either free option: a frontier vision model with drug-name world knowledge, run with
# adaptive thinking so it reasons over an unclear stroke before committing (see
# apps.prescriptions.services.ocr.anthropic). That path sends the prescription image (which
# can carry patient/doctor names) to Anthropic's API: don't switch it on without checking
# your data-handling/compliance posture first.
PRESCRIPTION_OCR_PROVIDER = os.getenv("PRESCRIPTION_OCR_PROVIDER", "tesseract")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# The strongest vision model is the point of this path - the handwriting it's for is exactly
# where a smaller model gives up. Override to claude-sonnet-5 to trade some accuracy for cost.
ANTHROPIC_OCR_MODEL = os.getenv("ANTHROPIC_OCR_MODEL", "claude-opus-5")

# PRESCRIPTION_OCR_PROVIDER="openai_vision" sends the scan to a vision-language model on any
# OpenAI-compatible /chat/completions endpoint that accepts image blocks (OpenRouter, a local
# Ollama with llama3.2-vision/qwen2-vl, Groq, ...). This is the non-Anthropic way to read
# *handwriting* - Tesseract and EasyOCR only do print. The image (which can carry patient/
# doctor names) leaves the box for a hosted gateway, so it is a data-handling decision, same
# as ANTHROPIC_API_KEY - just not tied to one vendor. _MODEL has no default: name a
# vision-capable model. Inert until all three of BASE_URL/API_KEY/MODEL are set.
PRESCRIPTION_OCR_VISION_BASE_URL = os.getenv("PRESCRIPTION_OCR_VISION_BASE_URL", "")
PRESCRIPTION_OCR_VISION_API_KEY = os.getenv("PRESCRIPTION_OCR_VISION_API_KEY", "")
PRESCRIPTION_OCR_VISION_MODEL = os.getenv("PRESCRIPTION_OCR_VISION_MODEL", "")
PRESCRIPTION_OCR_VISION_TIMEOUT_SECONDS = int(os.getenv("PRESCRIPTION_OCR_VISION_TIMEOUT_SECONDS", "45"))

# PRESCRIPTION_OCR_PROVIDER="vision_structured" (OpenAI-compatible gateway, reuses the
# PRESCRIPTION_OCR_VISION_* settings above) and "anthropic_structured" (Claude, reuses
# ANTHROPIC_API_KEY / ANTHROPIC_OCR_MODEL) are the best reads available here on handwriting.
# Both go from image straight to structured fields in ONE call instead of transcribing to
# plain text and re-parsing that text with PRESCRIPTION_NLP_PROVIDER. The split is what
# hurts on a scrawl: the page context that makes a stroke legible - layout, dose columns,
# a brace tying "after meals" to two drugs - is gone by the time the text is flat, and rows
# get lost. When one of these is selected PRESCRIPTION_NLP_PROVIDER is not consulted at all;
# if the call fails the pipeline falls back to the two-stage path rather than losing the
# upload. Same data-handling caveat as every other hosted provider - the image leaves the box.

# --- Prescription structured extraction (NLP) ------------------------------------------
# After OCR turns a scanned paper prescription into text, this step turns that text into
# structured fields - patient, prescriber, date, and each medication with its directions
# ("how to take it"), duration ("how long"), and refill count. A patient sees the result
# read-only on their upload; a pharmacist edits it on review.
#
# PRESCRIPTION_NLP_PROVIDER="regex" (the default) is deterministic and offline - it reuses
# apps.prescriptions.services.metadata + .extraction, no account, no external call.
#
# PRESCRIPTION_NLP_PROVIDER="openai_compatible" (+ _BASE_URL, _API_KEY, _MODEL) sends the OCR
# text to an OpenAI-compatible chat gateway (OpenRouter, a local Ollama, Groq, ...) for a
# real parse of messy layouts, falling back to the regex extractor on any error. This is
# NOT the Anthropic path - but the OCR text can still carry patient/doctor names, so the
# same data-handling/compliance check flagged on PRESCRIPTION_OCR_PROVIDER applies to
# whichever gateway you point this at. _MODEL has no default on purpose - name the model
# you mean to pay for rather than inheriting one that quietly changes cost.
PRESCRIPTION_NLP_PROVIDER = os.getenv("PRESCRIPTION_NLP_PROVIDER", "regex")
PRESCRIPTION_NLP_BASE_URL = os.getenv("PRESCRIPTION_NLP_BASE_URL", "")
PRESCRIPTION_NLP_API_KEY = os.getenv("PRESCRIPTION_NLP_API_KEY", "")
PRESCRIPTION_NLP_MODEL = os.getenv("PRESCRIPTION_NLP_MODEL", "")
# 45s (not 20) leaves room for the shared LLM_FALLBACK_* to answer - a thinking model on a
# free tier is slower than the primary, and a fallback that always times out is no fallback.
PRESCRIPTION_NLP_TIMEOUT_SECONDS = int(os.getenv("PRESCRIPTION_NLP_TIMEOUT_SECONDS", "45"))

# --- Shared LLM fallback endpoint ------------------------------------------------------
# Every OpenAI-compatible chat caller in the codebase - the assistant intent parser and
# reply composer (ASSISTANT_*), the analytics digest (ANALYTICS_AI_*), and prescription OCR
# + structuring (PRESCRIPTION_OCR_VISION_* / PRESCRIPTION_NLP_*) - tries its OWN gateway
# first and this one only if that call fails. One cheap/free key (e.g. a Google AI Studio
# Gemini key via its OpenAI-compatible endpoint,
# https://generativelanguage.googleapis.com/v1beta/openai) as a cushion when a primary
# provider is rate-limited or down. It is a cushion, not capacity: a free tier has its own
# hard limits, and each caller still degrades to its deterministic path if the fallback
# fails too. Inert unless all three are set. For the OCR fallback to work the model must be
# multimodal (gemini-2.5-flash is). Same data-handling note as the per-surface keys - the
# image or text still leaves the box.
LLM_FALLBACK_BASE_URL = os.getenv("LLM_FALLBACK_BASE_URL", "")
LLM_FALLBACK_API_KEY = os.getenv("LLM_FALLBACK_API_KEY", "")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "")

# --- WhatsApp ----------------------------------------------------------------------------
# The console provider logs messages instead of calling Meta's API, so dev/test needs no
# WhatsApp Business account. Point WHATSAPP_PROVIDER at "meta_cloud" and supply the token/
# phone-number-id to send real messages (see apps.messaging.providers.meta_cloud).
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "console")
WHATSAPP_GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")  # signs inbound webhook payloads (X-Hub-Signature-256)
WHATSAPP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en")
WHATSAPP_TEMPLATE_ORDER_STATUS = os.getenv("WHATSAPP_TEMPLATE_ORDER_STATUS", "pharmalink_order_status_v1")
WHATSAPP_TEMPLATE_REFILL_REMINDER = os.getenv("WHATSAPP_TEMPLATE_REFILL_REMINDER", "pharmalink_refill_reminder_v1")
WHATSAPP_TEMPLATE_PHARMACY_ALERT = os.getenv("WHATSAPP_TEMPLATE_PHARMACY_ALERT", "pharmalink_pharmacy_alert_v1")
WHATSAPP_TEMPLATE_PRESCRIPTION_EXPIRY = os.getenv("WHATSAPP_TEMPLATE_PRESCRIPTION_EXPIRY", "pharmalink_prescription_expiry_v1")
WHATSAPP_TEMPLATE_RENEWAL_DECISION = os.getenv("WHATSAPP_TEMPLATE_RENEWAL_DECISION", "pharmalink_renewal_decision_v1")
WHATSAPP_TEMPLATE_PAYMENT_FAILED = os.getenv("WHATSAPP_TEMPLATE_PAYMENT_FAILED", "pharmalink_payment_failed_v1")

# --- SMS (patient prescription delivery) -----------------------------------------------
# When a doctor issues a prescription it is texted to the patient's phone alongside the
# email. The console provider logs instead of calling AWS, so dev/test needs no AWS account.
# Set SMS_PROVIDER="aws_sns" to send real messages via AWS SNS Publish (see
# apps.messaging.sms.aws_sns and docs/DEPLOY_AWS.md); boto3 uses the environment / task-role
# credentials just like the S3 config above.
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "console")
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "")  # alphanumeric origination ID; unsupported in some countries (e.g. US/CA)
AWS_SNS_REGION_NAME = os.getenv("AWS_SNS_REGION_NAME", "eu-central-1")

# --- In-app assistant ---------------------------------------------------------------------
# The assistant answers by matching a message to one of a fixed set of intents, running one
# read-only lookup, and rendering a templated sentence from the result (see apps.assistant).
# No reply text is ever generated by a model - which is why a model is optional here at all.
#
# ASSISTANT_PARSER="keyword" (the default) means intent matching is pure keyword scoring: free,
# offline, and it declines anything it is not confident about. Point it at "openrouter" with a
# key and a model to have an OpenAI-compatible endpoint classify the messages keywords could
# not - still only choosing an intent name from the persona's own list, never handed another
# user's data.
#
# ASSISTANT_API_KEY additionally turns on apps.assistant.composer: once set (with
# ASSISTANT_MODEL), the reply for any intent backed by a tool is written by the model from
# that tool's JSON result, instead of the fixed template in apps.assistant.intents - this is
# the difference between "sounds like a form letter" and "sounds like an assistant". The
# composer never gets a tool of its own and never chooses what to read; it only describes data
# that has already been fetched. Every reply it writes is checked against that data before it
# ships (see is_grounded() in composer.py) and falls back to the template on any doubt, so
# turning this on cannot make an answer state a stock level, price or date that isn't real -
# it can only make a correct answer read more naturally. Set ASSISTANT_PARSER=openrouter
# alongside it for the full effect: better intent coverage, not just better sentences. Weigh
# both against the same data-handling question flagged on PRESCRIPTION_OCR_PROVIDER before
# switching either on: message text and the data behind a reply can carry whatever a patient
# chose to type or whatever the platform holds on them.
#
# ASSISTANT_MODEL has no default on purpose - name the model you actually want to pay for
# (e.g. "openai/gpt-4o-mini", "deepseek/deepseek-chat", "qwen/qwen-2.5-7b-instruct") rather
# than inheriting one that quietly changes cost.
ASSISTANT_PARSER = os.getenv("ASSISTANT_PARSER", "keyword")
ASSISTANT_BASE_URL = os.getenv("ASSISTANT_BASE_URL", "https://openrouter.ai/api/v1")
ASSISTANT_API_KEY = os.getenv("ASSISTANT_API_KEY", "")
ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", "")
ASSISTANT_TIMEOUT_SECONDS = int(os.getenv("ASSISTANT_TIMEOUT_SECONDS", "12"))
ASSISTANT_REFERER = os.getenv("ASSISTANT_REFERER", "https://healthconnect.app")
# Shown verbatim in the emergency redirect. Left blank rather than guessed: an assistant that
# prints the wrong emergency number is worse than one that says "your local emergency number".
ASSISTANT_EMERGENCY_NUMBER = os.getenv("ASSISTANT_EMERGENCY_NUMBER", "")

# --- Pharmacy analytics: narrative digest --------------------------------------------------
# Plain-language prose over the KPI numbers apps.analytics.services.kpis already computes -
# see docs/AI_FEATURES.md §5. Distinct from ASSISTANT_* above on purpose: that block drives
# the in-app chat widget and (per its own docstring) never lets a model write the reply text,
# only pick an intent name. This one is a model narrating a fixed, already-computed payload
# for the pharmacy owner's own analytics screen - a different risk profile and a different
# budget, so it gets its own key rather than sharing ASSISTANT_API_KEY.
#
# ANALYTICS_AI_PROVIDER="none" (the default) means the digest falls back to the existing
# rule-based Smart Insights cards (apps.analytics.services.insights) - no external call, no
# cost. Point it at "openai_compatible" with a base URL, key and model to narrate over any
# gateway that speaks the OpenAI /chat/completions shape - OpenRouter
# (https://openrouter.ai/api/v1), OpenCode Zen's compatible-model family
# (https://opencode.ai/zen/v1 - only its /chat/completions-routed models, not its native
# OpenAI/Anthropic/Google models, which use different endpoints this adapter doesn't speak),
# a local Ollama server, or similar.
ANALYTICS_AI_PROVIDER = os.getenv("ANALYTICS_AI_PROVIDER", "none")
ANALYTICS_AI_BASE_URL = os.getenv("ANALYTICS_AI_BASE_URL", "")
ANALYTICS_AI_API_KEY = os.getenv("ANALYTICS_AI_API_KEY", "")
ANALYTICS_AI_MODEL = os.getenv("ANALYTICS_AI_MODEL", "")

# --- Prescription fax back-up -------------------------------------------------------------
# PrescribeIT-style guaranteed delivery: when a prescription can't be emailed to the patient
# (no address on file, or the send fails), it's faxed instead. Console logs instead of
# calling a real fax gateway (see apps.eprescriptions.services.fax).
FAX_PROVIDER = os.getenv("FAX_PROVIDER", "console")

# --- Test isolation --------------------------------------------------------------------
# `manage.py test` must never reach a real LLM endpoint just because a developer keeps live
# keys in their local .env. Force every model-backed surface to its offline/deterministic
# path for the test run; a test that wants the model path still opts in explicitly with
# override_settings + a mocked transport.
import sys  # noqa: E402

if "test" in sys.argv:
    PRESCRIPTION_OCR_PROVIDER = "tesseract"
    PRESCRIPTION_NLP_PROVIDER = "regex"
    PRESCRIPTION_OCR_VISION_BASE_URL = PRESCRIPTION_OCR_VISION_API_KEY = PRESCRIPTION_OCR_VISION_MODEL = ""
    PRESCRIPTION_NLP_BASE_URL = PRESCRIPTION_NLP_API_KEY = PRESCRIPTION_NLP_MODEL = ""
    ASSISTANT_PARSER = "keyword"
    ASSISTANT_API_KEY = ASSISTANT_MODEL = ""
    ANALYTICS_AI_PROVIDER = "none"
    ANALYTICS_AI_BASE_URL = ANALYTICS_AI_API_KEY = ANALYTICS_AI_MODEL = ""
    LLM_FALLBACK_BASE_URL = LLM_FALLBACK_API_KEY = LLM_FALLBACK_MODEL = ""
    # A live SMS_PROVIDER=aws_sns in a developer's .env must never reach AWS during a test run.
    SMS_PROVIDER = "console"
