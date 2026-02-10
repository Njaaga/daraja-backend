"""
Production Django settings for dashboard_app project.
"""

from pathlib import Path
import os

# --------------------------------------------------
# BASE
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# SECURITY
# --------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "replace-me-in-production")
DEBUG = True

ALLOWED_HOSTS = [
    "api.darajatechnologies.ca",
    "darajatechnologies.ca",
    "www.darajatechnologies.ca",
    "reporting.darajatechnologies.ca",
    "18.220.106.255",
]

# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------
INSTALLED_APPS = [
    # Django default apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_extensions",

    # Local apps
    "dashboards",
    "tenants",
    "subscriptions",
]

# --------------------------------------------------
# MIDDLEWARE (ORDER MATTERS)
# --------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be first
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Tenant / subscription logic LAST
    "tenants.middleware.TenantMiddleware",
    "subscriptions.middleware.TenantSubscriptionMiddleware",
    "subscriptions.middleware.SubscriptionEnforcementMiddleware",
]

# --------------------------------------------------
# CORS & CSRF (fixed)
# --------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    "https://reporting.darajatechnologies.ca",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "x-tenant-slug",
    "accept",
    "origin",
    "x-csrftoken",
]

CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]

CSRF_TRUSTED_ORIGINS = [
    "https://reporting.darajatechnologies.ca",
]

FRONTEND_URL = "https://reporting.darajatechnologies.ca"

# --------------------------------------------------
# URLS & WSGI
# --------------------------------------------------
ROOT_URLCONF = "dashboard_app.urls"
WSGI_APPLICATION = "dashboard_app.wsgi.application"

# --------------------------------------------------
# TEMPLATES
# --------------------------------------------------
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

# --------------------------------------------------
# DATABASE (AWS RDS – PostgreSQL)
# --------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "darajareportapp",
        "USER": "darajareportuser",
        "PASSWORD": "darajaapp",
        "HOST": "darajareport-app.c746kqoy2uqe.us-east-2.rds.amazonaws.com",
        "PORT": "5432",
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "sslmode": "require",
        },
    }
}

# --------------------------------------------------
# AUTH & PASSWORDS
# --------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "tenants.auth_backend.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# --------------------------------------------------
# DJANGO REST FRAMEWORK
# --------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Allow signup / preflight requests without auth
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
}

# --------------------------------------------------
# INTERNATIONALIZATION
# --------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------
# STATIC FILES
# --------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# --------------------------------------------------
# DEFAULT PK
# --------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------
# EMAIL (SMTP)
# --------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.mailtrap.io"
EMAIL_HOST_USER = "811ff587441671"
EMAIL_HOST_PASSWORD = "4ea6d96c3a54cc"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "no-reply@darajatechnologies.ca"

# --------------------------------------------------
# STRIPE
# --------------------------------------------------

STRIPE_SECRET_KEY = "sk_test_51ScWR0RmVC1QU5lPZUt0aPkWsRf1JmelEUZVAQMkBoaiEXJ8qM0L67OHCs5vSdCNC0QJ87wCcMwgOet8nljkyejA00gBLav9IJ"
STRIPE_PUBLISHABLE_KEY = "pk_test_51ScWR0RmVC1QU5lP25HlClhQeBrsGTdakbyxp39Jl0FIThrlsIz6LPAoy5BOFUZctIdSC5OQFu0mY9O4G9MLT4H400lzx7zxmK"
STRIPE_WEBHOOK_SECRET = "whsec_3TrmAjNN5tdAtqvux04Yp7M9zsxZtJoo"

# --------------------------------------------------
# MISC
# --------------------------------------------------
APPEND_SLASH = True

QB_CLIENT_ID = "ABH2nzGHo5Sm9Iyf7FVHUKGgvxBVfzjYiX0DjwTiJ4vEj5RsH4"
QB_CLIENT_SECRET = "IXfmnq9FDvy8FoL9KorZjb9fTq6CjChjc0gMDzq5"
QB_REDIRECT_URI = "https://reporting.darajatechnologies.ca/api/oauth/quickbooks/callback/"

