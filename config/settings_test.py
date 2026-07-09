"""Settings para la suite de tests: SQLite en memoria, caché local, Celery eager."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

ANTHROPIC_API_KEY = "test-key-fake"
