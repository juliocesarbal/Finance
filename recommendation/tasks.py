"""Tareas Celery del motor de recomendaciones (secciones 5.1-5.3)."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_universe_scoring_task() -> dict:
    """Etapa 1 diaria sobre el universo + escalado asíncrono del top N."""
    from .pipeline import run_universe_scoring

    return run_universe_scoring(escalate=True, sync_agent=False)


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
    rate_limit="6/m",  # el agente puede tardar; sin ráfagas contra la API
)
def escalate_to_agent(ticker: str, mechanical_score: float | None = None) -> dict:
    """Etapa 2: verificación profunda de un activo del top N (sección 5.2)."""
    from market.models import Asset

    from .agent import AgentUnavailableError, run_agent_review

    asset = Asset.objects.get(ticker=ticker)
    try:
        review = run_agent_review(asset, mechanical_score=mechanical_score)
    except AgentUnavailableError as exc:
        logger.warning("Agente no disponible: %s", exc)
        return {"ticker": ticker, "status": "skipped", "reason": str(exc)}
    return {
        "ticker": ticker,
        "status": "ok",
        "agent_score": review.agent_score,
        "mechanical_score": review.mechanical_score,
        "divergence": review.divergence,
        "signal": review.signal,
    }
