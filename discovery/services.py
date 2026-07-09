"""Motor de descubrimiento de mercados emergentes (secciones 6, 13 y 14).

Construye URLs de Google News RSS con operadores avanzados, mapea la
frecuencia de menciones por tema y calcula el Emerging Market Score con
los pesos exactos de la sección 13. Cada reporte persiste su desglose
(auditabilidad, sección 18) y usa lenguaje prudente (sección 20).
"""
import logging
import re

from django.utils import timezone

from core.models import EvidenceSource
from core.sources import classify_domain
from market.models import Asset
from market.services import load_price_frame
from news.services import analyze_sentiment, fetch_rss_entries, google_news_rss_url
from risk.services import latest_risk

from .models import EmergingTopic, OpportunityReport, OpportunityType, RiskLevel

logger = logging.getLogger(__name__)

# Nichos iniciales (ejemplos de la sección 6)
DEFAULT_TOPICS = [
    ("IA aplicada a salud", '"AI healthcare" AND (investment OR funding)', OpportunityType.SECTOR, "5-10 años"),
    ("Chips especializados", '"AI chips" AND (demand OR investment)', OpportunityType.TECHNOLOGY, "3-5 años"),
    ("Energía nuclear modular", '"small modular reactor" AND (investment OR deal)', OpportunityType.SECTOR, "5-10 años"),
    ("Litio y baterías", '(lithium OR "battery technology") AND (demand OR supply)', OpportunityType.COMMODITY, "cíclico"),
    ("Ciberseguridad", 'cybersecurity AND (growth OR investment)', OpportunityType.SECTOR, "3-5 años"),
    ("Biotecnología", 'biotech AND (breakthrough OR approval OR funding)', OpportunityType.SECTOR, "5-10 años"),
    ("Tokenización de activos reales", '"real world assets" AND tokenization', OpportunityType.CRYPTO, "5+ años"),
    ("Stablecoins", 'stablecoin AND (regulation OR adoption)', OpportunityType.CRYPTO, "3-5 años"),
    ("Infraestructura de datos", '"data center" AND (investment OR demand)', OpportunityType.SECTOR, "3-5 años"),
    ("Fintech en países emergentes", 'fintech AND ("latin america" OR "emerging markets")', OpportunityType.SECTOR, "3-5 años"),
    ("Mercados latinoamericanos", '"latin america" AND (equities OR "stock market")', OpportunityType.COUNTRY, "3-5 años"),
]

INSTITUTIONAL_KEYWORDS = [
    "investment", "funding", "billion", "million", "venture", "ipo",
    "acquisition", "stake", "fund", "raises", "capital",
]
TECH_KEYWORDS = [
    "breakthrough", "patent", "launch", "prototype", "research",
    "development", "innovation", "technology",
]
TICKER_PATTERN = re.compile(r"\((?:NYSE|NASDAQ|AMEX):\s*([A-Z.]{1,6})\)|\$([A-Z]{1,6})\b")

# Pesos exactos de la sección 13
WEIGHTS = {
    "sector_growth": 0.20,
    "adoption_signals": 0.15,
    "institutional_investment": 0.15,
    "fundamentals": 0.15,
    "price_momentum": 0.10,
    "news_regulation": 0.10,
    "tech_activity": 0.10,
    "risk": 0.05,
}


def seed_topics() -> int:
    created = 0
    for name, query, category, horizon in DEFAULT_TOPICS:
        _, was_created = EmergingTopic.objects.get_or_create(
            name=name,
            defaults={"query": query, "category": category, "default_horizon": horizon},
        )
        created += int(was_created)
    return created


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _extract_tickers(text: str) -> set[str]:
    found = set()
    for match in TICKER_PATTERN.finditer(text):
        ticker = match.group(1) or match.group(2)
        if ticker:
            found.add(ticker.upper())
    return found


def _three_month_return(asset: Asset) -> float | None:
    df = load_price_frame(asset, days=95)
    if len(df) < 30:
        return None
    closes = df["close"].astype(float)
    return float(closes.iloc[-1] / closes.iloc[0] - 1.0)


def scan_topic(topic: EmergingTopic, limit: int = 40) -> dict:
    """Escanea el RSS del tema y calcula las features del score 13."""
    url = google_news_rss_url(topic.query, lang="en", country="US")
    entries = fetch_rss_entries(url, limit=limit)
    count = len(entries)

    sentiments, inst_hits, tech_hits = [], 0, 0
    candidate_tickers: set[str] = set()
    for entry in entries:
        text = f"{entry['title']} {entry['summary']}".lower()
        compound, _label = analyze_sentiment(entry["title"])
        sentiments.append(compound)
        inst_hits += any(k in text for k in INSTITUTIONAL_KEYWORDS)
        tech_hits += any(k in text for k in TECH_KEYWORDS)
        candidate_tickers |= _extract_tickers(f"{entry['title']} {entry['summary']}")

    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

    # Solo se vinculan activos que ya existen en la base (lo demás queda
    # como candidato en el desglose, para curaduría manual vía admin)
    related_assets = list(Asset.objects.filter(ticker__in=candidate_tickers))

    fundamental_scores, returns, risk_scores = [], [], []
    for asset in related_assets:
        ratios = asset.fundamental_ratios.order_by("-as_of").first()
        if ratios and ratios.fundamental_score is not None:
            fundamental_scores.append(ratios.fundamental_score)
        ret = _three_month_return(asset)
        if ret is not None:
            returns.append(ret)
        metrics = latest_risk(asset)
        if metrics and metrics.risk_score is not None:
            risk_scores.append(metrics.risk_score)

    previous = topic.mention_count
    momentum = (count - previous) / previous if previous else 0.0

    features = {
        # 20% crecimiento del sector → momentum de menciones
        "sector_growth": _clamp(50.0 + momentum * 100.0),
        # 15% señales de adopción → volumen de cobertura (30 notas = 100)
        "adoption_signals": _clamp(count * (100.0 / 30.0)),
        # 15% inversión institucional → proporción de notas con señales de capital
        "institutional_investment": _clamp((inst_hits / count * 250.0) if count else 0.0),
        # 15% fundamentos → promedio de los activos relacionados (neutral sin datos)
        "fundamentals": (
            sum(fundamental_scores) / len(fundamental_scores)
            if fundamental_scores else 50.0
        ),
        # 10% momentum de precio → retorno 3m promedio de los relacionados
        "price_momentum": (
            _clamp(50.0 + (sum(returns) / len(returns)) * 200.0) if returns else 50.0
        ),
        # 10% noticias y regulación → sentimiento agregado de la cobertura
        "news_regulation": _clamp(50.0 + avg_sentiment * 50.0),
        # 10% actividad tecnológica → proporción de notas técnicas
        "tech_activity": _clamp((tech_hits / count * 250.0) if count else 0.0),
        # 5% riesgo → score de riesgo promedio (sin datos = incertidumbre alta)
        "risk": (sum(risk_scores) / len(risk_scores)) if risk_scores else 40.0,
    }
    score = round(sum(WEIGHTS[k] * v for k, v in features.items()), 1)

    topic.previous_mention_count = previous
    topic.mention_count = count
    topic.momentum = round(momentum, 3)
    topic.last_scanned_at = timezone.now()
    topic.save()

    return {
        "topic": topic,
        "score": score,
        "features": {k: round(v, 1) for k, v in features.items()},
        "entries": entries,
        "avg_sentiment": round(avg_sentiment, 3),
        "candidate_tickers": sorted(candidate_tickers),
        "related_assets": related_assets,
        "inst_hits": inst_hits,
        "tech_hits": tech_hits,
    }


def _risk_level_for(features: dict, related_assets: list) -> str:
    risk_component = features["risk"]
    if not related_assets:
        return RiskLevel.VERY_HIGH  # sin activos analizables = especulativo
    if risk_component >= 75:
        return RiskLevel.MEDIUM
    if risk_component >= 55:
        return RiskLevel.HIGH
    if risk_component >= 35:
        return RiskLevel.VERY_HIGH
    return RiskLevel.EXTREME


def build_report(scan: dict) -> OpportunityReport:
    """Genera el reporte de oportunidad (estructura sección 14)."""
    topic: EmergingTopic = scan["topic"]
    features = scan["features"]
    entries = scan["entries"]
    score = scan["score"]

    top_headlines = [e["title"] for e in entries[:5]]
    thesis_lines = [
        f"Tema: {topic.name} (consulta: {topic.query}).",
        f"Cobertura de prensa: {topic.mention_count} menciones en el último escaneo "
        f"(momentum {topic.momentum:+.0%} vs escaneo anterior).",
        f"Sentimiento agregado de titulares: {scan['avg_sentiment']:+.2f} (escala -1 a 1).",
        f"Señales de inversión institucional en {scan['inst_hits']} notas; "
        f"actividad tecnológica en {scan['tech_hits']}.",
    ]
    if scan["candidate_tickers"]:
        thesis_lines.append(
            "Tickers mencionados en la cobertura: "
            + ", ".join(scan["candidate_tickers"][:10])
            + (" (solo los ya cargados en el sistema se vinculan como activos relacionados)."),
        )
    if top_headlines:
        thesis_lines.append("Titulares destacados:")
        thesis_lines.extend(f"  · {h}" for h in top_headlines)

    risks_lines = [
        "- Señal construida principalmente sobre frecuencia y tono de prensa: "
        "puede reflejar hype mediático y no adopción real (sección 8.4).",
        "- Datos fundamentales limitados a los activos ya cargados en el sistema.",
        "- Los nichos emergentes suelen tener alta volatilidad y baja liquidez.",
    ]
    if not scan["related_assets"]:
        risks_lines.append(
            "- Sin activos analizables vinculados: tratar como oportunidad "
            "especulativa hasta validar con fuentes primarias (sección 7)."
        )

    conclusion = (
        f"Emerging Market Score {score}/100. "
        + (
            "Candidato para seguimiento y análisis más profundo con fuentes primarias."
            if score >= 60
            else "Oportunidad emergente especulativa: conviene analizar más antes de cualquier exposición."
        )
        + " Esta evaluación es educativa y no constituye asesoramiento financiero."
    )

    report = OpportunityReport.objects.create(
        topic=topic,
        name=topic.name,
        opportunity_type=topic.category,
        thesis="\n".join(thesis_lines),
        risks="\n".join(risks_lines),
        horizon=topic.default_horizon,
        risk_level=_risk_level_for(features, scan["related_assets"]),
        score=score,
        score_breakdown={"weights": WEIGHTS, "features": features},
        conclusion=conclusion,
    )
    report.related_assets.set(scan["related_assets"])

    evidence_ids = []
    for entry in entries[:5]:
        evidence = EvidenceSource.objects.create(
            url=(entry.get("url") or "")[:1000],
            source_name=entry.get("source") or "Google News",
            source_type=classify_domain(entry.get("source_url") or entry.get("url") or ""),
            published_at=entry.get("published_at"),
            relevant_excerpt=entry.get("title") or "",
        )
        evidence_ids.append(evidence.id)
    report.evidence.set(evidence_ids)
    return report


def run_discovery(limit_per_topic: int = 40) -> dict:
    """Escanea todos los temas activos y genera/actualiza reportes."""
    seed_topics()
    results = {"scanned": 0, "errors": 0, "reports": []}
    for topic in EmergingTopic.objects.filter(is_active=True):
        try:
            scan = scan_topic(topic, limit=limit_per_topic)
            report = build_report(scan)
            results["scanned"] += 1
            results["reports"].append(
                {"topic": topic.name, "score": report.score, "risk_level": report.risk_level}
            )
        except Exception:
            logger.exception("Error escaneando tema %s", topic.name)
            results["errors"] += 1
    results["reports"].sort(key=lambda r: -r["score"])
    return results
