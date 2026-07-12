"""Agente de verificación y decisión final (sección 5.2).

Implementado sobre la API de Anthropic con tool use: el agente decide qué
revisar (técnico, fundamentos, noticias, consenso, riesgo) leyendo SIEMPRE
de la base local, y entrega su veredicto vía la herramienta `submit_review`
con schema estricto (JSON validado, no texto libre).

Guardrails:
- Solo puede citar evidencia que efectivamente recibió en esta sesión
  (los ids inventados se descartan y se registra la anomalía).
- La justificación pasa por el filtro de frases prohibidas (sección 20)
  antes de persistirse.
- El score del agente no pisa al mecánico: ambos se guardan (15.10).

Se invoca desde una tarea Celery (`escalate_to_agent`), nunca en el request
del usuario (sección 16.1).
"""
import json
import logging

from django.conf import settings
from pydantic import BaseModel, Field, field_validator

from experts.services import latest_consensus, sync_consensus
from fundamentals.services import latest_ratios
from market.models import Asset
from market.services import latest_technical_snapshot
from news.models import News
from news.services import news_score
from risk.services import latest_risk

from .guardrails import sanitize_text
from .models import AgentReview, Signal
from .scoring import _market_data_evidence, _statements_evidence

logger = logging.getLogger(__name__)

MAX_TURNS = 12


class AgentUnavailableError(Exception):
    """No hay ANTHROPIC_API_KEY configurada ni cliente inyectado."""


class AgentFailedError(Exception):
    """El agente no entregó un veredicto válido."""


class AgentVerdict(BaseModel):
    """Salida estructurada del agente (sección 5.2, punto 3)."""

    final_signal: str
    confidence: float = Field(description="0-100")
    adjusted_score: float = Field(description="0-100, puede diferir del mecánico")
    justification: str
    contradictions_detected: list[str] = Field(default_factory=list)
    cited_evidence_ids: list[int] = Field(default_factory=list)

    @field_validator("final_signal")
    @classmethod
    def _valid_signal(cls, v: str) -> str:
        if v not in Signal.values:
            raise ValueError(f"Señal inválida: {v}")
        return v

    @field_validator("confidence", "adjusted_score")
    @classmethod
    def _clamp_0_100(cls, v: float) -> float:
        return max(0.0, min(100.0, float(v)))


SYSTEM_PROMPT = """Sos el agente de verificación de un sistema de análisis de inversiones.
Tu tarea: revisar el conjunto de datos consolidado de un activo y emitir un veredicto
estructurado que detecte lo que una fórmula lineal no puede ver — contradicciones entre
bloques de información (ej.: fundamentos sólidos pero racha de noticias regulatorias
negativas; score técnico alto con consenso de analistas muy disperso).

Reglas obligatorias:
1. Usá las herramientas para revisar los datos que necesites antes de decidir.
   Los datos vienen de la base local del sistema, con evidencia identificada por
   `evidence_id` y nivel de confiabilidad ya calculado (A+ a E).
2. Solo podés citar `evidence_id` que hayan aparecido en los resultados de tus
   herramientas en esta conversación. No inventes datos ni fuentes.
3. La dispersión alta entre analistas es una señal a mencionar explícitamente,
   no a promediar y esconder.
4. Lenguaje prudente obligatorio: jamás uses frases absolutas como "compra segura",
   "ganancia garantizada", "esta acción va a subir" o "no hay riesgo". Usá formas
   como "señal de compra moderada", "candidato para seguimiento", "riesgo alto",
   "no hay consenso suficiente".
5. Tu score ajustado puede diferir del mecánico: si diverge de forma significativa,
   explicá por qué — esa divergencia se muestra al usuario.
6. Cuando termines tu revisión, llamá a la herramienta `submit_review` con tu
   veredicto completo. La justificación debe estar en español, anclada a los datos
   que efectivamente recuperaste.
"""


def _ticker_schema() -> dict:
    return {
        "type": "object",
        "properties": {"ticker": {"type": "string", "description": "Ticker del activo"}},
        "required": ["ticker"],
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "get_technical_snapshot",
        "description": "Snapshot técnico actual: score 0-100, señales (SMA, RSI, MACD, volumen), soportes y resistencias.",
        "input_schema": _ticker_schema(),
    },
    {
        "name": "get_fundamentals",
        "description": "Tablero fundamental completo: múltiplos de precio, EV, rentabilidad, liquidez/solvencia y DCF con supuestos explícitos.",
        "input_schema": _ticker_schema(),
    },
    {
        "name": "get_news_digest",
        "description": "Digest de noticias recientes ya clasificadas (sentimiento, impacto, categoría, confiabilidad de la fuente).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "description": "Ventana en días (default 14)"},
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_analyst_consensus",
        "description": "Consenso de analistas: distribución compra/mantener/venta, precios objetivo y dispersión.",
        "input_schema": _ticker_schema(),
    },
    {
        "name": "get_risk_metrics",
        "description": "Métricas de riesgo: volatilidad anual, max drawdown, beta, correlaciones y score de riesgo (100 = bajo).",
        "input_schema": _ticker_schema(),
    },
    {
        "name": "submit_review",
        "description": "Entrega el veredicto final estructurado. Llamala una sola vez, al terminar la revisión.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "final_signal": {
                    "type": "string",
                    "enum": ["strong_buy", "moderate_buy", "hold", "high_risk", "avoid"],
                },
                "confidence": {"type": "number", "description": "Confianza 0-100"},
                "adjusted_score": {"type": "number", "description": "Score ajustado 0-100"},
                "justification": {
                    "type": "string",
                    "description": "Justificación en español, prudente y anclada a los datos revisados.",
                },
                "contradictions_detected": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Contradicciones explícitas entre bloques de información.",
                },
                "cited_evidence_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "IDs de evidencia que aparecieron en tus herramientas.",
                },
            },
            "required": [
                "final_signal", "confidence", "adjusted_score",
                "justification", "contradictions_detected", "cited_evidence_ids",
            ],
            "additionalProperties": False,
        },
    },
]


class AgentSession:
    """Ejecuta las herramientas del agente contra la base local y registra
    qué evidencia se le mostró (para validar citas después)."""

    def __init__(self, asset: Asset):
        self.asset = asset
        self.shown_evidence_ids: set[int] = set()

    def _register(self, evidence) -> int | None:
        if evidence is None:
            return None
        self.shown_evidence_ids.add(evidence.id)
        return evidence.id

    def get_technical_snapshot(self, **_) -> dict:
        snapshot = latest_technical_snapshot(self.asset)
        evidence_id = self._register(_market_data_evidence(self.asset))
        if snapshot is None:
            return {"error": "Histórico insuficiente para análisis técnico.", "evidence_id": evidence_id}
        return {**snapshot, "evidence_id": evidence_id}

    def get_fundamentals(self, **_) -> dict:
        ratios = latest_ratios(self.asset)
        if ratios is None:
            return {"error": "Sin fundamentales (los criptoactivos no tienen estados contables — sección 12)."}
        evidence_id = self._register(_statements_evidence(self.asset))
        fields = [
            "per", "forward_per", "peg", "price_to_book", "price_to_sales",
            "dividend_yield", "fcf_yield", "ev_ebitda", "ev_ebit", "ev_fcf", "ev_sales",
            "roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin",
            "current_ratio", "quick_ratio", "net_debt_to_ebitda", "interest_coverage",
            "debt_to_equity", "wacc", "dcf_fair_value", "dcf_upside", "fundamental_score",
        ]
        data = {f: getattr(ratios, f) for f in fields}
        data["dcf_assumptions"] = ratios.dcf_assumptions
        data["as_of"] = str(ratios.as_of)
        data["evidence_id"] = evidence_id
        return data

    def get_news_digest(self, days: int = 14, **_) -> dict:
        from django.utils import timezone

        score, count = news_score(self.asset, days=days)
        since = timezone.now() - timezone.timedelta(days=days)
        items = []
        for n in (
            News.objects.filter(asset=self.asset, published_at__gte=since)
            .select_related("evidence")
            .order_by("-impact_score")[:10]
        ):
            evidence_id = self._register(n.evidence)
            items.append(
                {
                    "title": n.title,
                    "category": n.category,
                    "sentiment": n.sentiment,
                    "impact_score": n.impact_score,
                    "source": n.source,
                    "reliability_level": n.evidence.reliability_level if n.evidence else None,
                    "reliability_score": n.evidence.reliability_score if n.evidence else None,
                    "published_at": str(n.published_at),
                    "evidence_id": evidence_id,
                }
            )
        return {"news_score": score, "item_count": count, "days": days, "top_items": items}

    def get_analyst_consensus(self, **_) -> dict:
        consensus = latest_consensus(self.asset)
        if consensus is None:
            try:
                consensus = sync_consensus(self.asset)
            except Exception:
                consensus = None
        if consensus is None:
            return {"error": "Sin consenso de analistas disponible para este activo."}
        from core.models import EvidenceSource, SourceType

        evidence = EvidenceSource.objects.filter(
            related_asset=self.asset, source_name="Consenso de analistas (vía yfinance)"
        ).first()
        if evidence is None:
            evidence = EvidenceSource.objects.create(
                url=f"https://finance.yahoo.com/quote/{self.asset.ticker}/analysis",
                source_name="Consenso de analistas (vía yfinance)",
                source_type=SourceType.INSTITUTIONAL,
                related_asset=self.asset,
                relevant_excerpt="Distribución de recomendaciones y precios objetivo.",
            )
        evidence_id = self._register(evidence)
        return {
            "as_of": str(consensus.as_of),
            "strong_buy": consensus.strong_buy,
            "buy": consensus.buy,
            "hold": consensus.hold,
            "sell": consensus.sell,
            "strong_sell": consensus.strong_sell,
            "total_analysts": consensus.total_analysts,
            "rating_mean": consensus.rating_mean,
            "mean_target": consensus.mean_target,
            "high_target": consensus.high_target,
            "low_target": consensus.low_target,
            "current_price": consensus.current_price,
            "dispersion": consensus.dispersion,
            "change_alert": consensus.change_alert,
            "evidence_id": evidence_id,
        }

    def get_risk_metrics(self, **_) -> dict:
        metrics = latest_risk(self.asset)
        evidence_id = self._register(_market_data_evidence(self.asset))
        if metrics is None:
            return {"error": "Riesgo no calculado todavía.", "evidence_id": evidence_id}
        return {
            "as_of": str(metrics.as_of),
            "volatility_annual": metrics.volatility_annual,
            "max_drawdown": metrics.max_drawdown,
            "beta": metrics.beta,
            "correlations": metrics.correlations,
            "risk_score": metrics.risk_score,
            "notes": metrics.notes,
            "evidence_id": evidence_id,
        }

    def execute(self, name: str, tool_input: dict) -> str:
        handler = getattr(self, name, None)
        if handler is None:
            return json.dumps({"error": f"Herramienta desconocida: {name}"})
        try:
            result = handler(**{k: v for k, v in tool_input.items() if k != "ticker"})
        except Exception as exc:
            logger.exception("Error ejecutando herramienta %s", name)
            return json.dumps({"error": str(exc)})
        return json.dumps(result, ensure_ascii=False, default=str)


def _get_client():
    if not settings.ANTHROPIC_API_KEY:
        raise AgentUnavailableError(
            "Configurá ANTHROPIC_API_KEY en .env para correr el agente de verificación."
        )
    import anthropic
    import httpx

    # En esta red el handshake TLS hacia api.anthropic.com es lento de forma
    # intermitente: con el connect timeout default (5 s) y 2 reintentos las
    # corridas fallan en ráfaga. Más margen y más reintentos lo absorben.
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=httpx.Timeout(600.0, connect=20.0),
        max_retries=4,
    )


def run_agent_review(
    asset: Asset,
    mechanical_score: float | None = None,
    client=None,
    max_turns: int = MAX_TURNS,
) -> AgentReview:
    """Corre el loop agéntico completo y persiste el AgentReview (15.10)."""
    if client is None:
        client = _get_client()

    if mechanical_score is None:
        latest = asset.recommendations.order_by("-created_at").first()
        mechanical_score = latest.score if latest else 50.0

    session = AgentSession(asset)
    messages = [
        {
            "role": "user",
            "content": (
                f"Revisá el activo {asset.ticker} ({asset.name or 'sin nombre'}, "
                f"tipo: {asset.asset_type}). Su score mecánico actual (fórmula 5.1) "
                f"es {mechanical_score}/100. Investigá con las herramientas, detectá "
                "contradicciones y entregá tu veredicto con submit_review."
            ),
        }
    ]

    verdict: AgentVerdict | None = None
    for turn in range(max_turns):
        force_submit = turn == max_turns - 1
        kwargs = {
            "model": settings.AGENT_MODEL,
            "max_tokens": 16000,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "messages": messages,
        }
        if force_submit:
            # tool_choice forzado es incompatible con thinking → se omite thinking
            kwargs["tool_choice"] = {"type": "tool", "name": "submit_review"}
        else:
            kwargs["thinking"] = {"type": "adaptive"}

        response = client.messages.create(**kwargs)

        if response.stop_reason == "refusal":
            raise AgentFailedError("El modelo rechazó la solicitud (stop_reason=refusal).")

        tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        submit = next((t for t in tool_uses if t.name == "submit_review"), None)
        if submit is not None:
            verdict = AgentVerdict.model_validate(submit.input)
            break

        if not tool_uses:
            # Sin herramientas y sin veredicto: pedirle que cierre.
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": "Cerrá tu análisis ahora llamando a submit_review con tu veredicto.",
                }
            )
            continue

        messages.append({"role": "assistant", "content": response.content})
        # Todos los tool_result en UN solo mensaje user (requisito de la API)
        results = [
            {
                "type": "tool_result",
                "tool_use_id": tool.id,
                "content": session.execute(tool.name, dict(tool.input)),
            }
            for tool in tool_uses
        ]
        messages.append({"role": "user", "content": results})

    if verdict is None:
        raise AgentFailedError(f"El agente no entregó veredicto en {max_turns} turnos.")

    # Guardrail sección 20: sanear frases absolutas antes de persistir
    justification, removed = sanitize_text(verdict.justification)
    contradictions = []
    for c in verdict.contradictions_detected:
        clean, extra = sanitize_text(c)
        contradictions.append(clean)
        removed.extend(extra)

    # Guardrail: solo evidencia realmente mostrada en la sesión
    cited = [i for i in verdict.cited_evidence_ids if i in session.shown_evidence_ids]
    invented = set(verdict.cited_evidence_ids) - set(cited)
    if invented:
        logger.warning(
            "El agente citó evidencia no mostrada (%s) para %s; se descarta.",
            invented, asset.ticker,
        )

    review = AgentReview.objects.create(
        asset=asset,
        mechanical_score=mechanical_score,
        agent_score=verdict.adjusted_score,
        confidence=verdict.confidence,
        signal=verdict.final_signal,
        justification=justification,
        contradictions_detected=contradictions,
        model_used=settings.AGENT_MODEL,
        raw_output={
            "verdict": verdict.model_dump(),
            "phrases_removed_by_guardrail": removed,
            "invented_evidence_ids_discarded": sorted(invented),
        },
    )
    review.evidence_sources.set(cited)
    logger.info(
        "AgentReview %s: mecánico %.1f vs agente %.1f (divergencia %.1f)",
        asset.ticker, mechanical_score, verdict.adjusted_score, review.divergence,
    )
    return review
