"""Clasificación de dominios conocidos → tipo de fuente (secciones 8 y 9)."""
from urllib.parse import urlparse

from .models import SourceType

# Mapa curado de dominios (sección 8.1/8.3/8.4). Ampliable vía admin/curación.
KNOWN_DOMAINS = {
    # Fuentes primarias / reguladores (8.1)
    "sec.gov": SourceType.OFFICIAL_FILING,
    "federalreserve.gov": SourceType.REGULATOR,
    "ecb.europa.eu": SourceType.REGULATOR,
    "imf.org": SourceType.REGULATOR,
    "worldbank.org": SourceType.REGULATOR,
    "oecd.org": SourceType.REGULATOR,
    # Medios financieros confiables (8.3)
    "reuters.com": SourceType.FINANCIAL_MEDIA,
    "bloomberg.com": SourceType.FINANCIAL_MEDIA,
    "ft.com": SourceType.FINANCIAL_MEDIA,
    "wsj.com": SourceType.FINANCIAL_MEDIA,
    "cnbc.com": SourceType.FINANCIAL_MEDIA,
    "marketwatch.com": SourceType.FINANCIAL_MEDIA,
    "finance.yahoo.com": SourceType.FINANCIAL_MEDIA,
    "yahoo.com": SourceType.FINANCIAL_MEDIA,
    "nasdaq.com": SourceType.FINANCIAL_MEDIA,
    "coindesk.com": SourceType.FINANCIAL_MEDIA,
    "theblock.co": SourceType.FINANCIAL_MEDIA,
    "investing.com": SourceType.FINANCIAL_MEDIA,
    "morningstar.com": SourceType.INSTITUTIONAL,
    "spglobal.com": SourceType.INSTITUTIONAL,
    "moodys.com": SourceType.INSTITUTIONAL,
    "fitchratings.com": SourceType.INSTITUTIONAL,
    "msci.com": SourceType.INSTITUTIONAL,
    # Señales sociales (8.4) — peso bajo por regla central
    "reddit.com": SourceType.SOCIAL,
    "twitter.com": SourceType.SOCIAL,
    "x.com": SourceType.SOCIAL,
    "youtube.com": SourceType.SOCIAL,
    "substack.com": SourceType.SOCIAL,
    "stocktwits.com": SourceType.SOCIAL,
    "news.ycombinator.com": SourceType.SOCIAL,
    "medium.com": SourceType.SOCIAL,
    "seekingalpha.com": SourceType.INDEPENDENT_ANALYST,
    "fool.com": SourceType.INDEPENDENT_ANALYST,
    "zacks.com": SourceType.INDEPENDENT_ANALYST,
    "benzinga.com": SourceType.FINANCIAL_MEDIA,
    "tipranks.com": SourceType.INDEPENDENT_ANALYST,
    "marketbeat.com": SourceType.INDEPENDENT_ANALYST,
}


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify_domain(url: str) -> SourceType:
    """Tipo de fuente según dominio; desconocidos → analista independiente
    (nivel C): ni se premia ni se castiga sin datos (sección 9)."""
    host = domain_of(url)
    if not host:
        return SourceType.PROMOTIONAL
    if host in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[host]
    # subdominios (p. ej. es.investing.com)
    for known, stype in KNOWN_DOMAINS.items():
        if host.endswith("." + known):
            return stype
    return SourceType.INDEPENDENT_ANALYST
