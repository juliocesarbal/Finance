"""Cálculo de riesgo por activo y cartera (sección 4.8).

`risk_score` es 0-100 con 100 = bajo riesgo, para que en la fórmula 5.1
(20% riesgo) un activo menos riesgoso aporte más puntos. Determinista,
con penalizaciones documentadas y test de regresión (16.6).
"""
import logging
import math

import pandas as pd
from django.utils import timezone

from market.models import Asset, AssetType
from market.services import load_price_frame

from .models import AssetRiskMetrics

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
CRYPTO_PENALTY = 15.0  # sección 12: mayor exigencia para criptoactivos


def _daily_returns(asset: Asset, days: int = 365) -> pd.Series:
    df = load_price_frame(asset, days=days)
    if df.empty or len(df) < 30:
        return pd.Series(dtype=float)
    returns = df["close"].astype(float).pct_change(fill_method=None).dropna()
    # Normaliza el índice a fecha para poder alinear activos con distintos
    # horarios de cierre (cripto 24/7 vs bolsa).
    returns.index = pd.to_datetime(returns.index).date
    return returns[~pd.Index(returns.index).duplicated(keep="last")]


def compute_asset_risk(
    asset: Asset,
    benchmark_ticker: str = "SPY",
    peer_tickers: list[str] | None = None,
    days: int = 365,
    persist: bool = True,
) -> dict:
    """Volatilidad anual, max drawdown, beta vs benchmark y correlaciones."""
    returns = _daily_returns(asset, days=days)
    notes: list[str] = []
    if returns.empty:
        return {
            "ticker": asset.ticker, "volatility_annual": None, "max_drawdown": None,
            "beta": None, "correlations": {}, "risk_score": None,
            "notes": ["Histórico insuficiente para calcular riesgo (mínimo 30 barras)."],
        }

    vol_annual = float(returns.std() * math.sqrt(TRADING_DAYS))

    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    max_dd = float(drawdown.min())

    # Beta vs benchmark (SPY debe estar en la watchlist/base)
    beta = None
    benchmark = Asset.objects.filter(ticker=benchmark_ticker).first()
    if benchmark and benchmark.id != asset.id:
        bench_returns = _daily_returns(benchmark, days=days)
        joined = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
        if len(joined) >= 30:
            var_bench = float(joined.iloc[:, 1].var())
            if var_bench > 0:
                beta = float(joined.iloc[:, 0].cov(joined.iloc[:, 1]) / var_bench)
        else:
            notes.append(f"Pocas fechas comunes con {benchmark_ticker} para beta.")
    elif benchmark is None:
        notes.append(f"Benchmark {benchmark_ticker} sin datos en la base; beta omitida.")

    # Correlaciones con pares (por defecto, el resto del universo activo)
    correlations: dict[str, float] = {}
    if peer_tickers is None:
        peer_tickers = list(
            Asset.objects.filter(is_active=True)
            .exclude(id=asset.id)
            .values_list("ticker", flat=True)[:10]
        )
    for peer_ticker in peer_tickers:
        peer = Asset.objects.filter(ticker=peer_ticker).first()
        if not peer or peer.id == asset.id:
            continue
        peer_returns = _daily_returns(peer, days=days)
        joined = pd.concat([returns, peer_returns], axis=1, join="inner").dropna()
        if len(joined) >= 30:
            correlations[peer_ticker] = round(float(joined.corr().iloc[0, 1]), 3)

    # Score 0-100 (100 = bajo riesgo), penalizaciones acotadas y documentadas
    score = 100.0
    score -= min(45.0, vol_annual * 80.0)              # vol 0.25 → −20 ; 0.5 → −40
    score -= min(25.0, abs(max_dd) * 50.0)             # dd −30% → −15
    if beta is not None:
        score -= min(10.0, abs(beta - 1.0) * 10.0)     # alejarse del mercado penaliza
    else:
        score -= 5.0
        notes.append("Beta no disponible: se aplica penalización por incertidumbre.")
    if asset.asset_type == AssetType.CRYPTO:
        score -= CRYPTO_PENALTY
        notes.append(
            "Criptoactivo: penalización adicional por riesgo de manipulación, "
            "liquidez y regulación (sección 12)."
        )
    score = round(max(0.0, min(100.0, score)), 1)

    result = {
        "ticker": asset.ticker,
        "volatility_annual": round(vol_annual, 4),
        "max_drawdown": round(max_dd, 4),
        "beta": round(beta, 3) if beta is not None else None,
        "correlations": correlations,
        "risk_score": score,
        "notes": notes,
    }

    if persist:
        AssetRiskMetrics.objects.create(
            asset=asset,
            as_of=timezone.now(),
            lookback_days=days,
            volatility_annual=result["volatility_annual"],
            max_drawdown=result["max_drawdown"],
            beta=result["beta"],
            benchmark=benchmark_ticker,
            correlations=correlations,
            risk_score=score,
            notes=notes,
        )
    return result


def latest_risk(asset: Asset) -> AssetRiskMetrics | None:
    return asset.risk_metrics.order_by("-as_of").first()


def risk_summary_text(metrics: AssetRiskMetrics | None, asset: Asset) -> list[str]:
    """Riesgos en lenguaje claro para las recomendaciones (regla sección 18:
    toda recomendación incluye riesgos explícitos)."""
    risks: list[str] = []
    if metrics is None:
        risks.append("Riesgo no calculado todavía: tratar como incertidumbre alta.")
        return risks
    if metrics.volatility_annual is not None and metrics.volatility_annual > 0.35:
        risks.append(
            f"Volatilidad anualizada elevada ({metrics.volatility_annual:.0%})."
        )
    if metrics.max_drawdown is not None and metrics.max_drawdown < -0.30:
        risks.append(
            f"Caída máxima histórica reciente de {metrics.max_drawdown:.0%} desde máximos."
        )
    if metrics.beta is not None and metrics.beta > 1.3:
        risks.append(f"Beta {metrics.beta:.2f}: amplifica los movimientos del mercado.")
    if asset.asset_type == AssetType.CRYPTO:
        risks.append(
            "Criptoactivo: riesgo regulatorio, de liquidez y de manipulación "
            "superiores a activos tradicionales (sección 12)."
        )
    if not risks:
        risks.append("Riesgo de mercado general: ningún activo está libre de pérdidas.")
    return risks
