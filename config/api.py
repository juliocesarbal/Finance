"""API raíz (Django Ninja): un router por app de dominio, montada en /api."""
from django.db import connection
from ninja import NinjaAPI

from discovery.api import router as discovery_router
from experts.api import router as experts_router
from fundamentals.api import router as fundamentals_router
from market.api import router as market_router
from market.providers import get_rate_limit_error_count
from news.api import router as news_router
from portfolio.api import router as portfolio_router
from recommendation.api import router as recommendation_router
from risk.api import router as risk_router
from simulation.api import router as simulation_router

api = NinjaAPI(
    title="Sistema Inteligente de Análisis, Simulación y Descubrimiento de Inversiones",
    version="0.1.0",
    description=(
        "Backend del sistema descrito en sistema_inversiones_inteligente_v2.md. "
        "Herramienta educativa y de apoyo: no reemplaza asesoramiento financiero "
        "profesional (sección 20)."
    ),
)

api.add_router("/market", market_router, tags=["market"])
api.add_router("/news", news_router, tags=["news"])
api.add_router("/fundamentals", fundamentals_router, tags=["fundamentals"])
api.add_router("/portfolio", portfolio_router, tags=["portfolio"])
api.add_router("/simulation", simulation_router, tags=["simulation"])
api.add_router("/risk", risk_router, tags=["risk"])
api.add_router("/recommendation", recommendation_router, tags=["recommendation"])
api.add_router("/experts", experts_router, tags=["experts"])
api.add_router("/discovery", discovery_router, tags=["discovery"])


@api.get("/health", tags=["health"])
def health(request):
    """Salud del sistema, incluida la métrica de errores 429 (sección 16.5)."""
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        db_ok = False

    from django.core.cache import cache

    cache_ok = True
    try:
        cache.set("health:ping", "pong", 10)
        cache_ok = cache.get("health:ping") == "pong"
    except Exception:
        cache_ok = False

    return {
        "status": "ok" if (db_ok and cache_ok) else "degraded",
        "database": db_ok,
        "cache": cache_ok,
        "yfinance_rate_limit_errors": get_rate_limit_error_count(),
    }
