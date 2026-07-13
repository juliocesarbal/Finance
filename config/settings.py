"""
Configuración del Sistema Inteligente de Análisis, Simulación y
Descubrimiento de Inversiones. Variables de entorno vía django-environ (.env).
"""
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    # Orígenes desde los que Django acepta mutaciones con cookie de sesión.
    # Los navegadores mandan header Origin en cada POST y el proxy de Next
    # reescribe el Host, así que hay que confiar explícitamente en el front.
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:3000", "http://127.0.0.1:3000"]),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/1"),
    ANTHROPIC_API_KEY=(str, ""),
    AGENT_MODEL=(str, "claude-opus-4-8"),
    AGENT_TOP_N=(int, 10),
    AGENT_SCORE_THRESHOLD=(float, 65.0),
    WATCHLIST=(list, [
        "AAPL", "MSFT", "NVDA", "TSLA", "SPY",
        "VOO", "QQQ", "BTC-USD", "ETH-USD", "SOL-USD",
    ]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-solo-desarrollo")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "corsheaders",
    # Cuentas: registro/login por sesión (email como identificador)
    "accounts",
    # Apps de dominio (sección 4 del documento)
    "core",
    "market",
    "fundamentals",
    "news",
    "portfolio",
    "simulation",
    "risk",
    "recommendation",
    "discovery",
    "experts",
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

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# CACHE_URL=locmemcache:// permite desarrollar sin Redis levantado;
# con Redis (docker compose) usar la URL redis:// (default).
_cache_url = env("CACHE_URL", default=env("REDIS_URL"))
if _cache_url.startswith("locmem"):
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _cache_url,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "finance",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------- Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = False

# Cadencia de ingesta (sección 19 V7 ajustable; intervalos conservadores
# para no forzar yfinance — sección 16.5)
CELERY_BEAT_SCHEDULE = {
    "ingest-prices": {
        "task": "market.tasks.ingest_prices_task",
        "schedule": crontab(minute="*/15"),
    },
    "compute-indicators": {
        "task": "market.tasks.compute_indicators_task",
        "schedule": crontab(minute="5,20,35,50"),
    },
    "ingest-news": {
        "task": "news.tasks.ingest_news_task",
        "schedule": crontab(minute=10),
    },
    "sync-fundamentals": {
        "task": "fundamentals.tasks.sync_fundamentals_task",
        "schedule": crontab(hour=6, minute=0),
    },
    "compute-risk": {
        "task": "risk.tasks.compute_risk_task",
        "schedule": crontab(hour=6, minute=30),
    },
    "sync-consensus": {
        "task": "experts.tasks.sync_consensus_task",
        "schedule": crontab(hour=7, minute=0),
    },
    "run-universe-scoring": {
        "task": "recommendation.tasks.run_universe_scoring_task",
        "schedule": crontab(hour=7, minute=30),
    },
    "run-discovery": {
        "task": "discovery.tasks.run_discovery_task",
        "schedule": crontab(day_of_week=1, hour=8, minute=0),
    },
}

# ------------------------------------------- Configuración del dominio
WATCHLIST = env("WATCHLIST")

# Agente de verificación (sección 5.2) y pipeline en dos etapas (5.3)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
AGENT_MODEL = env("AGENT_MODEL")
AGENT_TOP_N = env("AGENT_TOP_N")
AGENT_SCORE_THRESHOLD = env("AGENT_SCORE_THRESHOLD")

# Proveedor de datos de mercado (sección 16.5: interfaz swapeable)
MARKET_DATA_PROVIDER = "market.providers.YFinanceProvider"

# TTLs de caché por tipo de dato (segundos) — sección 16.5
MARKET_CACHE_TTLS = {
    "history_intraday": 300,       # 5 min
    "history_daily": 3600,         # 1 h
    "info": 6 * 3600,              # 6 h
    "financials": 24 * 3600,       # 24 h
    "news": 1800,                  # 30 min
    "recommendations": 12 * 3600,  # 12 h
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
