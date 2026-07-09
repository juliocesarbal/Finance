"""Tests del proveedor de datos (sección 16.5): caché, backoff y métrica 429."""
import pytest

from market import providers
from market.providers import (
    ProviderError,
    RateLimitedError,
    YFinanceProvider,
    get_rate_limit_error_count,
    normalize_news_item,
)


class YFRateLimitError(Exception):
    """Mismo nombre que la excepción real de yfinance."""


def test_cached_calls_fetch_once():
    provider = YFinanceProvider()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"value": 42}

    first = provider._cached("info", "test:key:1", fetch)
    second = provider._cached("info", "test:key:1", fetch)
    assert first == second == {"value": 42}
    assert calls["n"] == 1


def test_call_retries_on_rate_limit_and_records_metric(monkeypatch):
    provider = YFinanceProvider()
    sleeps: list[float] = []
    monkeypatch.setattr(providers.time, "sleep", lambda s: sleeps.append(s))

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise YFRateLimitError("429 Too Many Requests")
        return "ok"

    before = get_rate_limit_error_count()
    assert provider._call(flaky) == "ok"
    assert attempts["n"] == 3
    assert len(sleeps) == 2  # backoff entre reintentos
    assert sleeps[1] > sleeps[0]  # exponencial
    assert get_rate_limit_error_count() == before + 2


def test_call_raises_after_exhausting_retries(monkeypatch):
    provider = YFinanceProvider()
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)

    def always_limited():
        raise YFRateLimitError("429")

    with pytest.raises(RateLimitedError):
        provider._call(always_limited)


def test_call_wraps_other_errors_without_retry(monkeypatch):
    provider = YFinanceProvider()
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    def broken():
        attempts["n"] += 1
        raise ValueError("otro error")

    with pytest.raises(ProviderError):
        provider._call(broken)
    assert attempts["n"] == 1


def test_normalize_news_item_new_format():
    item = {
        "id": "abc",
        "content": {
            "title": "Apple presenta resultados",
            "summary": "Resumen",
            "pubDate": "2026-07-01T12:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://reuters.com/nota"},
        },
    }
    normalized = normalize_news_item(item)
    assert normalized["title"] == "Apple presenta resultados"
    assert normalized["source"] == "Reuters"
    assert normalized["url"] == "https://reuters.com/nota"
    assert normalized["published_at"].year == 2026


def test_normalize_news_item_old_format():
    item = {
        "title": "Nota vieja",
        "publisher": "CNBC",
        "link": "https://cnbc.com/nota",
        "providerPublishTime": 1_700_000_000,
    }
    normalized = normalize_news_item(item)
    assert normalized["source"] == "CNBC"
    assert normalized["url"] == "https://cnbc.com/nota"
    assert normalized["published_at"] is not None


def test_normalize_news_item_rejects_empty():
    assert normalize_news_item({}) is None
    assert normalize_news_item("no-dict") is None
