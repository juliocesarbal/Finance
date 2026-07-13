"""Ranking de oportunidades en dos etapas (sección 5.3).

Etapa 1 (barata): score mecánico 5.1 sobre TODO el universo activo.
Etapa 2 (cara, escalada): solo los activos que superan el umbral
(AGENT_SCORE_THRESHOLD) quedan en el top N (AGENT_TOP_N) y pasan al
agente de verificación 5.2. Así el costo de la API de Anthropic queda
acotado por el tamaño del top N, no por el universo completo.
"""
import logging
import threading

from django.conf import settings

from market.models import Asset

from .scoring import compute_mechanical_score, persist_recommendation

logger = logging.getLogger(__name__)

# Evita corridas superpuestas del fallback síncrono (una a la vez).
_agent_fallback_lock = threading.Lock()


def _broker_available(timeout: float = 2.0) -> bool:
    """Chequeo rápido del broker de Celery antes de encolar.

    Sin esto, cada `.delay()` con Redis caído bloquea el request reintentando
    la conexión durante minutos (kombu reintenta con backoff). Un solo ping
    con timeout corto acota el costo a ~2 s cuando el broker no está (B.3).
    """
    from config.celery import app as celery_app

    try:
        conn = celery_app.connection_for_write()
        try:
            conn.ensure_connection(max_retries=0, timeout=timeout)
        finally:
            conn.release()
        return True
    except Exception:
        return False


def _run_agent_reviews_in_background(candidates: list[dict]) -> bool:
    """Fallback sin Celery (B.3): corre las revisiones del agente en un hilo.

    Mantiene el espíritu de la sección 16.1 (el request del usuario no se
    bloquea esperando al LLM): el endpoint responde con el scoring mecánico
    y cada AgentReview se persiste a medida que el agente la termina.
    Devuelve False si ya hay una corrida en curso.
    """
    if not _agent_fallback_lock.acquire(blocking=False):
        return False

    def worker() -> None:
        from django.db import close_old_connections

        from .agent import AgentFailedError, AgentUnavailableError, run_agent_review

        try:
            for result in candidates:
                ticker = result["ticker"]
                try:
                    asset = Asset.objects.get(ticker=ticker)
                    review = run_agent_review(asset, mechanical_score=result["score"])
                    logger.info(
                        "AgentReview (fallback) OK para %s: agente %.1f",
                        ticker, review.agent_score,
                    )
                except (AgentUnavailableError, AgentFailedError) as exc:
                    logger.warning("Agente para %s: %s", ticker, exc)
                except Exception:
                    logger.exception("Agente (fallback) falló para %s", ticker)
                finally:
                    # Libera la conexión entre tickers: cada uno espera varios
                    # minutos al LLM, y sin este cierre el hilo la mantiene
                    # abierta e inactiva durante toda la corrida (puede agotar
                    # el pool de Postgres mientras el usuario navega el resto
                    # de la app).
                    close_old_connections()
        finally:
            _agent_fallback_lock.release()

    threading.Thread(target=worker, name="agent-reviews-fallback", daemon=True).start()
    return True


def run_universe_scoring(escalate: bool = True, sync_agent: bool = False) -> dict:
    """Etapa 1 sobre el universo; opcionalmente escala el top N a la etapa 2."""
    ranking: list[dict] = []
    errors = 0
    note = None

    for asset in Asset.objects.filter(is_active=True):
        try:
            result = compute_mechanical_score(asset)
            persist_recommendation(asset, result)
            ranking.append(result)
        except Exception:
            logger.exception("Error puntuando %s", asset.ticker)
            errors += 1

    ranking.sort(key=lambda r: r["score"], reverse=True)

    escalated: list[str] = []
    if escalate and ranking:
        threshold = settings.AGENT_SCORE_THRESHOLD
        top_n = settings.AGENT_TOP_N
        candidates = [r for r in ranking if r["score"] >= threshold][:top_n]
        if candidates and not sync_agent and not _broker_available():
            # Sin broker no se puede encolar; fallback en hilo si hay API key.
            if not settings.ANTHROPIC_API_KEY:
                note = (
                    "Etapa 2 (agente) omitida: no hay broker Celery/Redis ni "
                    "ANTHROPIC_API_KEY configurada en .env."
                )
                logger.warning(note)
            elif _run_agent_reviews_in_background(candidates):
                escalated = [r["ticker"] for r in candidates]
                note = (
                    "Sin broker Celery: el agente corre en segundo plano para "
                    f"{len(escalated)} activos ({', '.join(escalated)}). Los "
                    "resultados aparecen en el ranking a medida que terminan "
                    "(~1-2 min por activo)."
                )
                logger.warning(note)
            else:
                note = (
                    "Ya hay una corrida del agente en curso en segundo plano; "
                    "esperá a que termine antes de escalar de nuevo."
                )
                logger.warning(note)
            candidates = []
        for result in candidates:
            ticker = result["ticker"]
            if sync_agent:
                try:
                    from .agent import run_agent_review

                    asset = Asset.objects.get(ticker=ticker)
                    run_agent_review(asset, mechanical_score=result["score"])
                    escalated.append(ticker)
                except Exception:
                    logger.exception("Agente falló para %s", ticker)
            else:
                from .tasks import escalate_to_agent

                try:
                    escalate_to_agent.delay(ticker, result["score"])
                    escalated.append(ticker)
                except Exception:
                    # Broker Celery/Redis inactivo: el scoring mecánico ya quedó
                    # persistido; la etapa 2 es opcional y acotada (5.3).
                    logger.exception(
                        "No se pudo encolar la revisión del agente para %s "
                        "(¿Redis/Celery inactivos?)", ticker,
                    )
        if not candidates and note is None:
            logger.info(
                "Ningún activo superó el umbral %.0f: no se escala al agente "
                "(diseño 5.3: el gasto de LLM es opcional y acotado).", threshold,
            )

    return {
        "scored": len(ranking),
        "errors": errors,
        "escalated": escalated,
        "note": note,
        "ranking": [
            {"ticker": r["ticker"], "score": r["score"], "signal": r["signal"]}
            for r in ranking
        ],
    }
