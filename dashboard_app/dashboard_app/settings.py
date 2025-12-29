"""
Production Django settings for dashboard_app project.
"""

from pathlib import Path
import os

# Load environment variables from .env

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------
# SECURITY
# -------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "replace-me-in-production")

DEBUG = False

ALLOWED_HOSTS = [
    "18.220.106.255",         # Your EC2 public IP
    "yourdomain.com",         # Optional domain
]

# -------------------------------
# APPLICATIONS
# -------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework_simplejwt',
    'rest_framework',
    'dashboards',
    'tenants',
    'subscriptions',
    'corsheaders',
    'django_extensions',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "tenants.middleware.TenantMiddleware",
    'subscriptions.middleware.TenantSubscriptionMiddleware',
    'subscriptions.middleware.SubscriptionEnforcementMiddleware',
]

# -------------------------------
# CORS
# -------------------------------
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://daraja-frontend-dl85.vercel.app",
]
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "x-tenant-slug",
    "accept",
    "origin",
]
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

FRONTEND_URL = "https://daraja-frontend-dl85.vercel.app"

# -------------------------------
# URLS & TEMPLATES
# -------------------------------
ROOT_URLCONF = 'dashboard_app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dashboard_app.wsgi.application'

# -------------------------------
# DATABASE (PostgreSQL / RDS)
# -------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'darajareportapp',
        'USER': 'darajareportuser',
        'PASSWORD': 'darajaapp',
        'HOST': 'darajareport-app.c746kqoy2uqe.us-east-2.rds.amazonaws.com',
        'PORT': '5432',
        'CONN_MAX_AGE': 60,
        'OPTIONS': {
            'sslmode': 'require',  # REQUIRED for AWS RDS
        },
    }
}


# -------------------------------
# PASSWORD VALIDATION
# -------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# -------------------------------
# INTERNATIONALIZATION
# -------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# -------------------------------
# STATIC FILES (CSS/JS/Images)
# -------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

# Optional: global static directory
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# -------------------------------
# DEFAULT PRIMARY KEY
# -------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -------------------------------
# REST FRAMEWORK
# -------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
        'subscriptions.permissions.IsTenantSubscribed',
    ),
}

# -------------------------------
# EMAIL (production ready)
# -------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.mailtrap.io"
EMAIL_HOST_USER = "811ff587441671"
EMAIL_HOST_PASSWORD = "4ea6d96c3a54cc"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "no-reply@example.com"

# -------------------------------
# STRIPE KEYS (replace with prod)
# -------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# -------------------------------
# AUTH
# -------------------------------
APPEND_SLASH = True
AUTHENTICATION_BACKENDS = [
    'tenants.auth_backend.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]
