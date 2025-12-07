import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _decimal_env(key: str, default: str) -> Decimal:
    raw_value = os.getenv(key, default)
    try:
        return Decimal(raw_value)
    except (InvalidOperation, TypeError):
        return Decimal(default)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-default-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "quantstrike_backend.urls"

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
    }
]

WSGI_APPLICATION = "quantstrike_backend.wsgi.application"
ASGI_APPLICATION = "quantstrike_backend.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "quantstrike"),
        "USER": os.getenv("POSTGRES_USER", "quantstrike"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "quantstrike"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}

_additional_cors_origins = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://13.203.224.240",
    "http://ec2-13-203-224-240.ap-south-1.compute.amazonaws.com"
    *_additional_cors_origins,
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGIN_REGEXES = [pattern.strip() for pattern in os.getenv("CORS_ALLOWED_ORIGIN_REGEXES", "").split(",") if pattern.strip()]

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@quantstrike.local")

ANGEL_SANDBOX_ENABLED = os.getenv("ANGEL_SANDBOX_ENABLED", "false").lower() == "true"
ANGEL_INSTRUMENT_METADATA_PATH = os.getenv(
    "ANGEL_INSTRUMENT_METADATA_PATH",
    str((BASE_DIR.parent / "docs" / "smartapi-instrument-metadata.json").resolve()),
)
HISTORICAL_DATA_ROOT = os.getenv(
    "QUANTSTRIKE_HISTORICAL_DATA_ROOT",
    str((BASE_DIR.parent / "docs" / "historical-data").resolve()),
)

QUANTSTRIKE_BROKERAGE_PER_LEG = _decimal_env("QUANTSTRIKE_BROKERAGE_PER_LEG", "20")
QUANTSTRIKE_BROKERAGE_GST_RATE = _decimal_env("QUANTSTRIKE_BROKERAGE_GST_RATE", "0.18")
QUANTSTRIKE_MARGIN_BUFFER_MULTIPLIER = _decimal_env("QUANTSTRIKE_MARGIN_BUFFER_MULTIPLIER", "1")
