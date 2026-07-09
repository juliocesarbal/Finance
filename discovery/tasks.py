"""Tarea Celery del motor de descubrimiento (semanal)."""
from celery import shared_task


@shared_task
def run_discovery_task() -> dict:
    from .services import run_discovery

    return run_discovery()
