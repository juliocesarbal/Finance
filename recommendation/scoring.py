"""Capa mecánica del motor de recomendaciones (sección 5.1).

Fórmula determinista, sin LLM, que corre sobre todo el universo:
    30% técnico + 25% noticias/sentimiento + 25% fundamentos + 20% riesgo
Sirve como primer filtro, no como veredicto final (esa es la capa 5.2).
"""
import logging

from django.utils import timezone

from core.models import EvidenceSource, SourceType
from fundamentals.services import latest_ratios
from market.models import Asset, AssetType
from market.services import latest_technical_snapshot
from news.models import News
from news.services import news_score
from risk.services import latest_risk, risk_summary_text

from .models import Recommendation, Signal, signal_for_score

logger = logging.getLogger(__name__)

WEIGHTS = {"technical": 0.30, "news": 0.25, "fundamentals": 0.25, "risk": 0.20}
NEUTRAL = 50.0
CRYPTO_NO_FUNDAMENTALS_CAP = 64.0  # sección 12: nunca "compra" solo por precio


def compute_mechanical_score(asset: Asset) -> dict:
    """Calcula el score ponderado 5.1 con desglose completo y auditable."""
    flags: list[str] = []

    snapshot = latest_technical_snapshot(asset)
    if snapshot is None:
        technical, technical_signals = NEUTRAL, ["Sin histórico técnico suficiente."]
        flags.append("sin_datos_tecnicos")
    else:
        technical, technical_signals = snapshot["score"], snapshot["signals"]

    news_value, news_count = news_score(asset)
    if news_count == 0:
        flags.append("sin_noticias_recientes")

    ratios = latest_ratios(asset)
    if ratios is not None and ratios.fundamental_score is not None:
        fundamentals = ratios.fundamental_score
    else:
        fundamentals = NEUTRAL
        flags.append("sin_fundamentales")

    risk_metrics = latest_risk(asset)
    if risk_metrics is not None and risk_metrics.risk_score is not None:
        risk_value = risk_metrics.risk_score
    else:
        risk_value = NEUTRAL
        flags.append("sin_metricas_riesgo")

    total = (
        WEIGHTS["technical"] * technical
        + WEIGHTS["news"] * news_value
        + WEIGHTS["fundamentals"] * fundamentals
        + WEIGHTS["risk"] * risk_value
    )

    # Regla estricta para cripto (sección 12): sin fundamentos verificables,
    # un token no puede recibir señal de compra solo por momentum de precio.
    if asset.asset_type == AssetType.CRYPTO and "sin_fundamentales" in flags:
        if total > CRYPTO_NO_FUNDAMENTALS_CAP:
            total = CRYPTO_NO_FUNDAMENTALS_CAP
            flags.append("cripto_capado_sin_fundamentos")

    total = round(max(0.0, min(100.0, total)), 1)
    signal = signal_for_score(total)

    explanation = _build_explanation(
        asset, total, signal, technical, news_value, news_count,
        fundamentals, risk_value, technical_signals, ratios, flags,
    )
    risks = _build_risks(asset, risk_metrics, ratios, flags)

    return {
        "ticker": asset.ticker,
        "score": total,
        "signal": signal,
        "technical_score": round(technical, 1),
        "news_score": round(news_value, 1),
        "fundamental_score": round(fundamentals, 1),
        "risk_score": round(risk_value, 1),
        "explanation": explanation,
        "risks": risks,
        "flags": flags,
    }


def _build_explanation(
    asset, total, signal, technical, news_value, news_count,
    fundamentals, risk_value, technical_signals, ratios, flags,
) -> str:
    """Texto explicativo con el desglose (regla 18: todo auditable)."""
    lines = [
        f"Score mecánico {total}/100 → {Signal(signal).label} (fórmula 5.1).",
        "",
        f"- Técnico (30%): {technical:.0f}/100.",
    ]
    for s in technical_signals[:4]:
        lines.append(f"    · {s}")
    lines.append(
        f"- Noticias y sentimiento (25%): {news_value:.0f}/100 "
        f"({news_count} noticias en 14 días; 50 = neutral)."
    )
    if ratios is not None and ratios.fundamental_score is not None:
        detail = []
        if ratios.per is not None:
            detail.append(f"PER {ratios.per:.1f}")
        if ratios.roe is not None:
            detail.append(f"ROE {ratios.roe:.0%}")
        if ratios.net_margin is not None:
            detail.append(f"margen neto {ratios.net_margin:.0%}")
        if ratios.dcf_upside is not None:
            detail.append(f"DCF upside {ratios.dcf_upside:+.0%}")
        suffix = f" ({', '.join(detail)})" if detail else ""
        lines.append(f"- Fundamentos (25%): {fundamentals:.0f}/100{suffix}.")
    else:
        lines.append(
            "- Fundamentos (25%): 50/100 neutral — sin estados contables "
            "disponibles para este activo."
        )
    lines.append(f"- Riesgo (20%): {risk_value:.0f}/100 (100 = riesgo bajo).")
    if "cripto_capado_sin_fundamentos" in flags:
        lines.append(
            "- Ajuste sección 12: criptoactivo sin fundamentos verificables — "
            "el score se limita a 'mantener/observar' aunque el momentum sea positivo."
        )
    lines.append("")
    lines.append(
        "Conclusión prudente: esta señal es un primer filtro mecánico; "
        "no constituye asesoramiento financiero (sección 20)."
    )
    return "\n".join(lines)


def _build_risks(asset, risk_metrics, ratios, flags) -> str:
    """Riesgos explícitos (regla 18: ninguna recomendación sin riesgos claros)."""
    risks = risk_summary_text(risk_metrics, asset)
    if ratios is not None:
        if ratios.per is not None and ratios.per > 40:
            risks.append(f"Valoración exigente (PER {ratios.per:.0f}): sensible a decepciones.")
        if ratios.dcf_upside is not None and ratios.dcf_upside < -0.20:
            risks.append(
                f"El DCF sugiere sobrevaloración ({ratios.dcf_upside:.0%} vs precio actual), "
                "bajo los supuestos persistidos."
            )
        if ratios.net_debt_to_ebitda is not None and ratios.net_debt_to_ebitda > 3.5:
            risks.append(
                f"Apalancamiento elevado (deuda neta/EBITDA {ratios.net_debt_to_ebitda:.1f})."
            )
    if "sin_noticias_recientes" in flags:
        risks.append("Sin cobertura de prensa reciente: menor visibilidad de eventos.")
    return "\n".join(f"- {r}" for r in risks)


def _market_data_evidence(asset: Asset) -> EvidenceSource:
    """Evidencia canónica de los datos de mercado usados (fuente B, sección 9)."""
    evidence = EvidenceSource.objects.filter(
        related_asset=asset, source_name="Yahoo Finance (datos de mercado vía yfinance)"
    ).first()
    if evidence is None:
        evidence = EvidenceSource.objects.create(
            url=f"https://finance.yahoo.com/quote/{asset.ticker}",
            source_name="Yahoo Finance (datos de mercado vía yfinance)",
            source_type=SourceType.FINANCIAL_MEDIA,
            related_asset=asset,
            relevant_excerpt="Precios históricos, volumen e indicadores calculados.",
        )
    return evidence


def _statements_evidence(asset: Asset) -> EvidenceSource | None:
    """Evidencia de estados financieros (fuente primaria contable, sección 8.1)."""
    if not asset.statements.exists():
        return None
    evidence = EvidenceSource.objects.filter(
        related_asset=asset, source_name="Estados financieros de la empresa (vía yfinance)"
    ).first()
    if evidence is None:
        evidence = EvidenceSource.objects.create(
            url=f"https://finance.yahoo.com/quote/{asset.ticker}/financials",
            source_name="Estados financieros de la empresa (vía yfinance)",
            source_type=SourceType.OFFICIAL_FILING,
            related_asset=asset,
            relevant_excerpt="Balance, cuenta de resultados y flujo de caja (últimos 4 años fiscales).",
        )
    return evidence


def persist_recommendation(asset: Asset, result: dict) -> Recommendation:
    """Persiste la recomendación con sus fuentes explícitas (regla 18)."""
    recommendation = Recommendation.objects.create(
        asset=asset,
        signal=result["signal"],
        score=result["score"],
        technical_score=result["technical_score"],
        news_score=result["news_score"],
        fundamental_score=result["fundamental_score"],
        risk_score=result["risk_score"],
        explanation=result["explanation"],
        risks=result["risks"],
    )
    evidence = [_market_data_evidence(asset)]
    statements_ev = _statements_evidence(asset)
    if statements_ev:
        evidence.append(statements_ev)
    since = timezone.now() - timezone.timedelta(days=14)
    news_evidence = (
        News.objects.filter(asset=asset, published_at__gte=since, evidence__isnull=False)
        .order_by("-impact_score")
        .values_list("evidence_id", flat=True)[:5]
    )
    recommendation.evidence_sources.set(evidence + list(news_evidence))
    return recommendation


def score_and_persist(asset: Asset) -> Recommendation:
    return persist_recommendation(asset, compute_mechanical_score(asset))
