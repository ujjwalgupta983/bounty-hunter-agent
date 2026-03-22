"""
Django settings for Bounty Hunter Agent.
"""
import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(os.path.join(BASE_DIR, "config", ".env"))

SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-in-prod")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_filters",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    "drf_spectacular",
    # Local apps
    "bounty_hunter",
    "bounty_hunter.models",
    "bounty_hunter.scouts",
    "bounty_hunter.tracker",
    "bounty_hunter.solver",
    "bounty_hunter.submitter",
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

ROOT_URLCONF = "bounty_hunter.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "bounty_hunter.wsgi.application"

# Database
DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# REST Framework
# =============================================================================
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bounty Hunter Agent API",
    "DESCRIPTION": "AI-powered autonomous bounty hunter",
    "VERSION": "0.1.0",
}

# =============================================================================
# Celery
# =============================================================================
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND = "django-cache"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 3600  # 1 hour hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 3000  # 50 min soft limit
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50

# Celery Beat Schedule
CELERY_BEAT_SCHEDULE = {
    "scout-full-scan": {
        "task": "bounty_hunter.scouts.tasks.run_full_scan",
        "schedule": env.int("SCOUT_SCAN_INTERVAL_HOURS", default=2) * 3600,
    },
    "tracker-check-prs": {
        "task": "bounty_hunter.tracker.tasks.check_all_prs",
        "schedule": 3600,  # Every hour
    },
    "analyst-rescore-stale": {
        "task": "bounty_hunter.analyst.tasks.rescore_stale_bounties",
        "schedule": 86400,  # Daily
    },
    "tracker-ping-stale": {
        "task": "bounty_hunter.tracker.tasks.ping_stale_prs",
        "schedule": 604800,  # Weekly
    },
}

# =============================================================================
# Bounty Hunter Settings
# =============================================================================
BOUNTY_HUNTER = {
    # GitHub
    "GITHUB_TOKEN": env("GITHUB_TOKEN", default=""),
    "GITHUB_USERNAME": env("GITHUB_USERNAME", default=""),
    # AI — provider selection
    "AI_PROVIDER": env("ANALYST_AI_PROVIDER", default="anthropic"),  # anthropic | openai | openrouter
    "AI_MODEL": env("ANALYST_AI_MODEL", default=""),                 # blank = use provider default
    "ANTHROPIC_API_KEY": env("ANTHROPIC_API_KEY", default=""),
    "OPENAI_API_KEY": env("OPENAI_API_KEY", default=""),
    "OPENROUTER_API_KEY": env("OPENROUTER_API_KEY", default=""),
    "CODING_AGENT": env("SOLVER_CODING_AGENT", default="claude"),
    # Scout
    "MIN_BOUNTY_USD": env.int("SCOUT_MIN_BOUNTY_USD", default=50),
    "MAX_BOUNTY_AGE_DAYS": env.int("SCOUT_MAX_BOUNTY_AGE_DAYS", default=90),
    # Analyst
    "MIN_ROI_SCORE": env.float("ANALYST_MIN_ROI_SCORE", default=40.0),
    # Solver
    "MAX_CONCURRENT_SOLVERS": env.int("SOLVER_MAX_CONCURRENT", default=5),
    "SOLVER_TIMEOUT_MULTIPLIER": env.float("SOLVER_TIMEOUT_MULTIPLIER", default=2.0),
    "SOLVER_MAX_ITERATIONS": env.int("SOLVER_MAX_ITERATIONS", default=3),
    # Submitter
    "HUMAN_REVIEW_FIRST_N": env.int("SUBMITTER_HUMAN_REVIEW_FIRST_N", default=20),
    "SUBMIT_RATE_LIMIT_PER_HOUR": env.int("SUBMITTER_RATE_LIMIT_PER_HOUR", default=3),
    # Notifications
    "TELEGRAM_BOT_TOKEN": env("TELEGRAM_BOT_TOKEN", default=""),
    "TELEGRAM_CHAT_ID": env("TELEGRAM_CHAT_ID", default=""),
}

# CORS
CORS_ALLOW_ALL_ORIGINS = DEBUG
