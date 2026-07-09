"""Proveedor de datos falso: los tests jamás tocan la red (sección 16.6)."""
import pandas as pd

from market.providers import MarketDataProvider

from .helpers import make_price_frame


class FakeProvider(MarketDataProvider):
    def __init__(
        self,
        history: pd.DataFrame | None = None,
        info: dict | None = None,
        news: list | None = None,
        financials: dict | None = None,
        recommendations: dict | None = None,
    ):
        self._history = history if history is not None else make_price_frame()
        self._info = info or {}
        self._news = news or []
        self._financials = financials or {
            "income": pd.DataFrame(),
            "balance": pd.DataFrame(),
            "cashflow": pd.DataFrame(),
        }
        self._recommendations = recommendations or {"summary": [], "targets": {}}
        self.calls: list[tuple] = []

    def get_history(self, ticker, period="1y", interval="1d"):
        self.calls.append(("history", ticker, period, interval))
        return self._history

    def get_info(self, ticker):
        self.calls.append(("info", ticker))
        return self._info

    def get_news(self, ticker, limit=20):
        self.calls.append(("news", ticker))
        return self._news

    def get_financials(self, ticker):
        self.calls.append(("financials", ticker))
        return self._financials

    def get_recommendations(self, ticker):
        self.calls.append(("recommendations", ticker))
        return self._recommendations
