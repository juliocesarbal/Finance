"""Aplicación Celery. En Windows (desarrollo) correr el worker con --pool=solo."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("finance")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
