"""Ingesta dual de noticias (sección 4.4): yfinance `.news` para actualidad
corporativa + Google News RSS (feedparser) para lo sectorial/macro.

Cada noticia genera su EvidenceSource con confiabilidad calculada (sección 9).
El sentimiento usa VADER (léxico en inglés: para titulares en otros idiomas
la señal tiende a neutral, lo cual es un default conservador aceptable).
"""
import hashlib
import logging
from datetime import datetime, timezone as dt_timezone
from urllib.parse import quote_plus

import feedparser
import requests
from django.utils import timezone

from core.models import EvidenceSource, SourceType
from core.sources import classify_domain, domain_of
from market.providers import get_provider

from .models import News, NewsCategory, SentimentLabel

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; FinanceResearchBot/0.1)"

# Palabras clave por categoría (bilingüe es/en) — sección 4.4
CATEGORY_KEYWORDS = {
    NewsCategory.EARNINGS: [
        "earnings", "results", "revenue", "profit", "guidance", "quarterly",
        "resultados", "ingresos", "beneficio", "ganancias", "trimestre",
    ],
    NewsCategory.PRODUCTS: [
        "launch", "unveils", "new product", "release", "announces new",
        "lanzamiento", "presenta", "nuevo producto",
    ],
    NewsCategory.REGULATION: [
        "regulation", "regulator", "sec ", "antitrust", "compliance", "ban",
        "regulación", "regulador", "normativa", "prohibición", "multa",
    ],
    NewsCategory.LEGAL: [
        "lawsuit", "sued", "investigation", "probe", "settlement", "court",
        "demanda", "investigación", "juicio", "tribunal",
    ],
    NewsCategory.MNA: [
        "merger", "acquisition", "acquires", "buyout", "takeover", "deal to buy",
        "fusión", "adquisición", "compra de", "opa",
    ],
    NewsCategory.MANAGEMENT: [
        "ceo", "cfo", "resigns", "appoints", "steps down", "executive",
        "renuncia", "nombra", "directiva", "director ejecutivo",
    ],
    NewsCategory.CONTRACTS: [
        "contract", "agreement", "partnership", "supply deal", "wins deal",
        "contrato", "acuerdo", "alianza",
    ],
    NewsCategory.GEOPOLITICS: [
        "tariff", "sanctions", "geopolitical", "war", "export controls", "trade war",
        "arancel", "sanciones", "geopolítico", "guerra",
    ],
    NewsCategory.TECHNOLOGY: [
        "ai ", "artificial intelligence", "chip", "quantum", "breakthrough", "patent",
        "inteligencia artificial", "innovación", "patente", "tecnología",
    ],
}

# Impacto base 0-100 por categoría (heurística documentada y determinista)
CATEGORY_BASE_IMPACT = {
    NewsCategory.EARNINGS: 70.0,
    NewsCategory.MNA: 75.0,
    NewsCategory.REGULATION: 65.0,
    NewsCategory.LEGAL: 60.0,
    NewsCategory.CONTRACTS: 55.0,
    NewsCategory.GEOPOLITICS: 55.0,
    NewsCategory.PRODUCTS: 55.0,
    NewsCategory.MANAGEMENT: 50.0,
    NewsCategory.TECHNOLOGY: 50.0,
    NewsCategory.OTHER: 30.0,
}

_vader = None


def _get_vader():
    global _vader
    if _vader is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _vader = SentimentIntensityAnalyzer()
    return _vader


def analyze_sentiment(text: str) -> tuple[float, str]:
    """Devuelve (compound en [-1,1], etiqueta)."""
    if not text or not text.strip():
        return 0.0, SentimentLabel.NEUTRAL
    compound = _get_vader().polarity_scores(text)["compound"]
    if compound >= 0.05:
        label = SentimentLabel.POSITIVE
    elif compound <= -0.05:
        label = SentimentLabel.NEGATIVE
    else:
        label = SentimentLabel.NEUTRAL
    return round(compound, 4), label


def classify_category(text: str) -> str:
    """Clasificación por reglas de palabras clave (primera coincidencia con
    más matches gana; empate → orden de definición)."""
    lowered = f" {text.lower()} "
    best, best_hits = NewsCategory.OTHER, 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best, best_hits = category, hits
    return best


def estimate_impact(category: str, sentiment: float, reliability: float) -> float:
    """Impacto 0-100: base por categoría × intensidad del sentimiento
    × factor de confiabilidad de la fuente (0.6–1.0)."""
    base = CATEGORY_BASE_IMPACT.get(category, 30.0)
    intensity = 0.5 + abs(sentiment) / 2.0          # 0.5–1.0
    reliability_factor = 0.6 + 0.4 * (reliability / 100.0)  # 0.6–1.0
    return round(min(100.0, base * intensity * reliability_factor), 1)


def url_fingerprint(url: str, title: str) -> str:
    basis = url or title
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def google_news_rss_url(query: str, lang: str = "en", country: str = "US") -> str:
    """Construye la URL de Google News RSS con operadores avanzados (sección 6)."""
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={lang}&gl={country}&ceid={country}:{lang}"
    )


def fetch_rss_entries(url: str, limit: int = 30) -> list[dict]:
    """Descarga y parsea un feed RSS. Separado en función propia para poder
    mockearlo con `responses` en tests (sección 16.6)."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    entries = []
    for entry in feed.entries[:limit]:
        published_at = None
        if getattr(entry, "published_parsed", None):
            published_at = datetime(*entry.published_parsed[:6], tzinfo=dt_timezone.utc)
        source_title, source_url = "", ""
        if getattr(entry, "source", None) is not None:
            source_title = getattr(entry.source, "title", "") or ""
            source_url = getattr(entry.source, "href", "") or ""
        entries.append(
            {
                "title": getattr(entry, "title", "") or "",
                "summary": getattr(entry, "summary", "") or "",
                "url": getattr(entry, "link", "") or "",
                "source": source_title or domain_of(getattr(entry, "link", "")),
                # URL del medio original (Google News enlaza vía redirect):
                # permite clasificar la confiabilidad por dominio real
                "source_url": source_url,
                "published_at": published_at,
            }
        )
    return entries


def _persist_news_item(
    item: dict,
    asset=None,
    keyword: str = "",
    language: str = "en",
    default_source_type: str | None = None,
) -> News | None:
    """Crea News + EvidenceSource (dedupe por hash de URL). Devuelve None si ya existía."""
    title = (item.get("title") or "").strip()
    if not title:
        return None
    url = item.get("url") or ""
    fingerprint = url_fingerprint(url, title)
    if News.objects.filter(url_hash=fingerprint).exists():
        return None

    text = f"{title}. {item.get('summary') or ''}"
    sentiment, label = analyze_sentiment(text)
    category = classify_category(text)

    source_type = default_source_type or classify_domain(item.get("source_url") or url)
    evidence = EvidenceSource.objects.create(
        url=url[:1000],
        source_name=item.get("source") or domain_of(url) or "desconocida",
        source_type=source_type,
        author=item.get("author") or "",
        published_at=item.get("published_at"),
        related_asset=asset,
        relevant_excerpt=(item.get("summary") or title)[:500],
    )
    impact = estimate_impact(category, sentiment, evidence.reliability_score)

    return News.objects.create(
        asset=asset,
        keyword=keyword,
        title=title[:500],
        summary=item.get("summary") or "",
        source=item.get("source") or "",
        author=item.get("author") or "",
        url=url,
        url_hash=fingerprint,
        language=language,
        published_at=item.get("published_at"),
        sentiment=sentiment,
        sentiment_label=label,
        impact_score=impact,
        category=category,
        evidence=evidence,
    )


def ingest_asset_news(asset, limit: int = 20) -> int:
    """Noticias corporativas del ticker vía provider (yfinance `.news`)."""
    try:
        items = get_provider().get_news(asset.ticker, limit=limit)
    except Exception:
        logger.warning("Noticias yfinance no disponibles para %s", asset.ticker, exc_info=True)
        return 0
    created = 0
    for item in items:
        if _persist_news_item(item, asset=asset, language="en"):
            created += 1
    return created


def ingest_rss_for_query(
    query: str,
    asset=None,
    keyword: str = "",
    lang: str = "en",
    country: str = "US",
    limit: int = 30,
) -> int:
    """Noticias sectoriales/macro vía Google News RSS (sección 4.4)."""
    url = google_news_rss_url(query, lang=lang, country=country)
    try:
        entries = fetch_rss_entries(url, limit=limit)
    except Exception:
        logger.warning("RSS no disponible para query=%r", query, exc_info=True)
        return 0
    created = 0
    for entry in entries:
        if _persist_news_item(entry, asset=asset, keyword=keyword or query, language=lang):
            created += 1
    return created


def news_score(asset, days: int = 14) -> tuple[float, int]:
    """Score de noticias 0-100 para la capa mecánica (5.1): promedio del
    sentimiento ponderado por impacto × confiabilidad. 50 = neutral."""
    since = timezone.now() - timezone.timedelta(days=days)
    items = list(
        News.objects.filter(asset=asset, published_at__gte=since)
        .select_related("evidence")
        .only("sentiment", "impact_score", "evidence")
    )
    if not items:
        return 50.0, 0

    weighted_sum = 0.0
    weight_total = 0.0
    for item in items:
        reliability = item.evidence.reliability_score if item.evidence else 50.0
        weight = max(1.0, item.impact_score) * max(10.0, reliability)
        weighted_sum += item.sentiment * weight
        weight_total += weight
    avg_sentiment = weighted_sum / weight_total if weight_total else 0.0
    return round(max(0.0, min(100.0, 50.0 + avg_sentiment * 50.0)), 1), len(items)
