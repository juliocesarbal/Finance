"""Proveedor de datos de mercado (sección 16.5).

Aísla las llamadas a yfinance detrás de una interfaz propia
(`MarketDataProvider`) para poder swapear a un proveedor de pago
(Polygon, Alpha Vantage, Finnhub) sin tocar el resto del sistema.

Mitigaciones implementadas:
- Caché (Redis vía Django cache) con TTL distinto por tipo de dato.
- Backoff exponencial + reintentos ante rate limits (429).
- Contador de errores 429 como métrica de salud, no solo log.
"""
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone as dt_timezone

import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

RATE_LIMIT_METRIC_KEY = "metrics:yfinance:429"
INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}


class ProviderError(Exception):
    """Error genérico del proveedor de datos."""


class RateLimitedError(ProviderError):
    """El proveedor respondió 429 y se agotaron los reintentos."""


def record_rate_limit_error():
    """Métrica de salud de errores 429 (sección 16.5)."""
    try:
        cache.incr(RATE_LIMIT_METRIC_KEY)
    except ValueError:
        cache.set(RATE_LIMIT_METRIC_KEY, 1, timeout=7 * 86400)


def get_rate_limit_error_count() -> int:
    return int(cache.get(RATE_LIMIT_METRIC_KEY) or 0)


def _looks_like_rate_limit(exc: Exception) -> bool:
    name = type(exc).__name__
    text = str(exc).lower()
    return (
        name == "YFRateLimitError"
        or "429" in text
        or "too many requests" in text
        or "rate limit" in text
    )


class MarketDataProvider(ABC):
    """Interfaz swapeable de datos de mercado."""

    @abstractmethod
    def get_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """OHLCV con columnas open/high/low/close/volume e índice datetime."""

    @abstractmethod
    def get_info(self, ticker: str) -> dict:
        """Metadatos y ratios del activo (dict `.info`)."""

    @abstractmethod
    def get_news(self, ticker: str, limit: int = 20) -> list:
        """Noticias corporativas normalizadas: title/summary/url/source/published_at."""

    @abstractmethod
    def get_financials(self, ticker: str) -> dict:
        """Estados financieros anuales: {'income': df, 'balance': df, 'cashflow': df}."""

    @abstractmethod
    def get_recommendations(self, ticker: str) -> dict:
        """Consenso de analistas: {'summary': [...], 'targets': {...}}."""


class YFinanceProvider(MarketDataProvider):
    """Implementación sobre yfinance (no es API oficial: ver sección 8.5)."""

    max_retries = 3
    base_delay = 2.0

    # ------------------------------------------------------------ utilidades
    def _call(self, fn, *args, **kwargs):
        """Ejecuta una llamada a yfinance con reintentos y backoff exponencial."""
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # yfinance lanza tipos variados
                last_exc = exc
                if _looks_like_rate_limit(exc):
                    record_rate_limit_error()
                    delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Rate limit de yfinance (intento %s/%s); esperando %.1fs",
                        attempt + 1, self.max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                raise ProviderError(f"Fallo de yfinance: {exc}") from exc
        raise RateLimitedError(
            f"yfinance sigue limitando tras {self.max_retries} intentos: {last_exc}"
        )

    def _cached(self, ttl_kind: str, key: str, fetch):
        ttl = settings.MARKET_CACHE_TTLS.get(ttl_kind, 3600)
        hit = cache.get(key)
        if hit is not None:
            return hit
        value = fetch()
        if value is not None:
            cache.set(key, value, timeout=ttl)
        return value

    def _ticker(self, ticker: str):
        import yfinance as yf  # import perezoso: los tests no lo necesitan

        return yf.Ticker(ticker)

    # ------------------------------------------------------------- interfaz
    def get_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        ttl_kind = "history_intraday" if interval in INTRADAY_INTERVALS else "history_daily"
        key = f"yf:history:{ticker}:{period}:{interval}"

        def fetch():
            df = self._call(
                self._ticker(ticker).history,
                period=period, interval=interval, auto_adjust=True,
            )
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns=str.lower)
            cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            return df[cols]

        return self._cached(ttl_kind, key, fetch)

    def get_info(self, ticker: str) -> dict:
        key = f"yf:info:{ticker}"

        def fetch():
            info = self._call(self._ticker(ticker).get_info)
            return info or {}

        return self._cached("info", key, fetch)

    def get_news(self, ticker: str, limit: int = 20) -> list:
        key = f"yf:news:{ticker}:{limit}"

        def fetch():
            try:
                raw = self._call(self._ticker(ticker).get_news, count=limit)
            except ProviderError:
                logger.warning("No se pudieron obtener noticias de %s", ticker)
                return []
            return [n for n in (normalize_news_item(item) for item in raw or []) if n]

        return self._cached("news", key, fetch)

    def get_financials(self, ticker: str) -> dict:
        key = f"yf:financials:{ticker}"

        def fetch():
            t = self._ticker(ticker)
            out = {}
            for name, attr in (
                ("income", "income_stmt"),
                ("balance", "balance_sheet"),
                ("cashflow", "cashflow"),
            ):
                try:
                    df = self._call(getattr, t, attr)
                    out[name] = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
                except ProviderError:
                    out[name] = pd.DataFrame()
            return out

        return self._cached("financials", key, fetch)

    def get_recommendations(self, ticker: str) -> dict:
        key = f"yf:recommendations:{ticker}"

        def fetch():
            t = self._ticker(ticker)
            summary_rows, targets = [], {}
            try:
                df = self._call(getattr, t, "recommendations_summary")
                if isinstance(df, pd.DataFrame) and not df.empty:
                    summary_rows = df.to_dict(orient="records")
            except ProviderError:
                logger.warning("Sin resumen de recomendaciones para %s", ticker)
            try:
                raw_targets = self._call(getattr, t, "analyst_price_targets")
                if isinstance(raw_targets, dict):
                    targets = raw_targets
            except ProviderError:
                logger.warning("Sin precios objetivo para %s", ticker)
            return {"summary": summary_rows, "targets": targets}

        return self._cached("recommendations", key, fetch)


def normalize_news_item(item: dict) -> dict | None:
    """Normaliza una noticia de yfinance (formato viejo plano o nuevo con
    'content' anidado) a un dict estable para la app news."""
    if not isinstance(item, dict):
        return None
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = content.get("title") or ""
    if not title:
        return None

    url = ""
    for candidate in (
        (content.get("canonicalUrl") or {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else None,
        (content.get("clickThroughUrl") or {}).get("url") if isinstance(content.get("clickThroughUrl"), dict) else None,
        item.get("link"),
        content.get("link"),
    ):
        if candidate:
            url = candidate
            break

    provider = content.get("provider")
    if isinstance(provider, dict):
        source = provider.get("displayName") or ""
    else:
        source = item.get("publisher") or ""

    published_at = None
    pub = content.get("pubDate") or content.get("displayTime")
    epoch = item.get("providerPublishTime")
    if isinstance(pub, str):
        try:
            published_at = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except ValueError:
            published_at = None
    elif isinstance(epoch, (int, float)):
        published_at = datetime.fromtimestamp(epoch, tz=dt_timezone.utc)

    return {
        "title": title,
        "summary": content.get("summary") or content.get("description") or "",
        "url": url,
        "source": source or "Yahoo Finance",
        "published_at": published_at,
    }


_provider: MarketDataProvider | None = None


def get_provider() -> MarketDataProvider:
    """Singleton del proveedor configurado en settings.MARKET_DATA_PROVIDER."""
    global _provider
    if _provider is None:
        cls = import_string(settings.MARKET_DATA_PROVIDER)
        _provider = cls()
    return _provider


def set_provider(provider: MarketDataProvider | None):
    """Permite inyectar un proveedor falso en tests."""
    global _provider
    _provider = provider
