"""Ranking de oportunidades en dos etapas (sección 5.3).

Etapa 1 (barata): score mecánico 5.1 sobre TODO el universo activo.
Etapa 2 (cara, escalada): solo los activos que superan el umbral
(AGENT_SCORE_THRESHOLD) quedan en el top N (AGENT_TOP_N) y pasan al
agente de verificación 5.2. Así el costo de la API de Anthropic queda
acotado por el tamaño del top N, no por el universo completo.
"""
import logging

from django.conf import settings

from market.models import Asset

from .scoring import compute_mechanical_score, persist_recommendation

logger = logging.getLogger(__name__)


def run_universe_scoring(escalate: bool = True, sync_agent: bool = False) -> dict:
    """Etapa 1 sobre el universo; opcionalmente escala el top N a la etapa 2."""
    ranking: list[dict] = []
    errors = 0

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

                escalate_to_agent.delay(ticker, result["score"])
                escalated.append(ticker)
        if not candidates:
            logger.info(
                "Ningún activo superó el umbral %.0f: no se escala al agente "
                "(diseño 5.3: el gasto de LLM es opcional y acotado).", threshold,
            )

    return {
        "scored": len(ranking),
        "errors": errors,
        "escalated": escalated,
        "ranking": [
            {"ticker": r["ticker"], "score": r["score"], "signal": r["signal"]}
            for r in ranking
        ],
    }
