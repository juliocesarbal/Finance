"""Cálculo del tablero fundamental completo (sección 4.3, bloques 1-5).

Los indicadores que `yfinance` trae directo en `.info` se toman de ahí;
el resto se calcula desde los estados financieros. El DCF/WACC persiste sus
supuestos explícitos (regla de auditabilidad, sección 18).
"""
import logging
import math

import pandas as pd
from django.utils import timezone

from market.models import Asset, AssetType
from market.providers import get_provider

from .models import FinancialStatement, FundamentalRatios, StatementType

logger = logging.getLogger(__name__)

# Etiquetas candidatas en los estados de yfinance (varían por empresa)
LINE_ALIASES = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "ebit": ["EBIT", "Operating Income"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "pretax_income": ["Pretax Income"],
    "tax_expense": ["Tax Provision", "Income Tax Expense"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
    "inventory": ["Inventory"],
    "equity": ["Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"],
    "total_debt": ["Total Debt"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "free_cash_flow": ["Free Cash Flow"],
    "operating_cash_flow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
}

# Supuestos por defecto del DCF (siempre quedan persistidos junto al resultado)
DCF_DEFAULTS = {
    "projection_years": 5,
    "terminal_growth": 0.025,
    "risk_free_rate": 0.042,
    "equity_risk_premium": 0.05,
    "default_cost_of_debt": 0.05,
    "default_tax_rate": 0.21,
    "growth_cap": 0.20,
    "growth_floor": 0.0,
    "default_growth": 0.06,
    "wacc_floor": 0.06,
    "wacc_cap": 0.16,
}


def _clean(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _line(df: pd.DataFrame, key: str, col: int = 0) -> float | None:
    """Busca una línea contable por sus alias en la columna `col` (0 = año más reciente)."""
    if df is None or df.empty or col >= len(df.columns):
        return None
    for alias in LINE_ALIASES.get(key, [key]):
        if alias in df.index:
            return _clean(df.loc[alias].iloc[col])
    return None


def _normalize_dividend_yield(value) -> float | None:
    """yfinance cambió el formato (0.0055 vs 0.55): normaliza a fracción."""
    v = _clean(value)
    if v is None:
        return None
    return v / 100.0 if v > 0.3 else v


def _normalize_debt_to_equity(value) -> float | None:
    """yfinance lo expone en porcentaje (150 = 1.5x): normaliza a ratio."""
    v = _clean(value)
    if v is None:
        return None
    return v / 100.0 if v > 10 else v


def persist_statements(asset: Asset, financials: dict) -> int:
    """Guarda los estados anuales crudos (hasta 4 años fiscales, sección 4.3)."""
    stored = 0
    type_map = {
        "income": StatementType.INCOME,
        "balance": StatementType.BALANCE,
        "cashflow": StatementType.CASHFLOW,
    }
    for kind, df in financials.items():
        if df is None or getattr(df, "empty", True):
            continue
        for col in list(df.columns)[:4]:
            try:
                period = pd.Timestamp(col).date()
            except (ValueError, TypeError):
                continue
            data = {str(idx): _clean(df.loc[idx, col]) for idx in df.index}
            FinancialStatement.objects.update_or_create(
                asset=asset,
                statement_type=type_map[kind],
                period_ending=period,
                defaults={"data": data},
            )
            stored += 1
    return stored


def compute_dcf(info: dict, financials: dict, price: float | None) -> dict:
    """DCF a 5 años + valor terminal, descontado al WACC (bloque 5).

    Devuelve dict con fair_value, upside, wacc y los supuestos usados.
    """
    a = dict(DCF_DEFAULTS)
    cashflow = financials.get("cashflow")

    fcf = _clean(info.get("freeCashflow"))
    if fcf is None:
        fcf = _line(cashflow, "free_cash_flow")
    if fcf is None:
        ocf = _line(cashflow, "operating_cash_flow")
        capex = _line(cashflow, "capex")
        if ocf is not None and capex is not None:
            fcf = ocf + capex  # capex viene con signo negativo

    market_cap = _clean(info.get("marketCap"))
    total_debt = _clean(info.get("totalDebt")) or 0.0
    cash = _clean(info.get("totalCash")) or 0.0
    shares = _clean(info.get("sharesOutstanding"))
    beta = _clean(info.get("beta")) or 1.0

    growth = _clean(info.get("earningsGrowth"))
    if growth is None:
        growth = _clean(info.get("revenueGrowth"))
    if growth is None:
        growth = a["default_growth"]
    growth = max(a["growth_floor"], min(a["growth_cap"], growth))

    # WACC = CAPM para el equity + costo de deuda después de impuestos
    cost_equity = a["risk_free_rate"] + beta * a["equity_risk_premium"]
    cost_debt_after_tax = a["default_cost_of_debt"] * (1 - a["default_tax_rate"])
    if market_cap and (market_cap + total_debt) > 0:
        we = market_cap / (market_cap + total_debt)
    else:
        we = 1.0
    wacc = we * cost_equity + (1 - we) * cost_debt_after_tax
    wacc = max(a["wacc_floor"], min(a["wacc_cap"], wacc))

    assumptions = {
        **a,
        "fcf_base": fcf,
        "growth_used": round(growth, 4),
        "beta_used": beta,
        "cost_of_equity": round(cost_equity, 4),
        "wacc_used": round(wacc, 4),
        "net_debt": total_debt - cash,
        "shares_outstanding": shares,
    }

    if not fcf or fcf <= 0 or not shares or wacc <= a["terminal_growth"]:
        return {"fair_value": None, "upside": None, "wacc": wacc, "assumptions": assumptions}

    pv_total = 0.0
    projected = fcf
    for year in range(1, a["projection_years"] + 1):
        projected *= (1 + growth)
        pv_total += projected / (1 + wacc) ** year

    terminal = projected * (1 + a["terminal_growth"]) / (wacc - a["terminal_growth"])
    pv_total += terminal / (1 + wacc) ** a["projection_years"]

    equity_value = pv_total - (total_debt - cash)
    fair_value = equity_value / shares if shares else None
    upside = (fair_value / price - 1.0) if (fair_value and price) else None

    return {
        "fair_value": round(fair_value, 2) if fair_value else None,
        "upside": round(upside, 4) if upside is not None else None,
        "wacc": round(wacc, 4),
        "assumptions": assumptions,
    }


def compute_ratios(asset: Asset, info: dict, financials: dict) -> dict:
    """Calcula los 5 bloques de la sección 4.3."""
    income = financials.get("income")
    balance = financials.get("balance")

    price = _clean(info.get("currentPrice")) or _clean(info.get("regularMarketPrice"))
    market_cap = _clean(info.get("marketCap"))

    revenue = _line(income, "revenue")
    gross_profit = _line(income, "gross_profit")
    ebit = _line(income, "ebit")
    ebitda = _clean(info.get("ebitda")) or _line(income, "ebitda")
    net_income = _line(income, "net_income")
    pretax = _line(income, "pretax_income")
    tax = _line(income, "tax_expense")
    interest = _line(income, "interest_expense")
    total_debt = _clean(info.get("totalDebt")) or _line(balance, "total_debt")
    cash = _clean(info.get("totalCash")) or _line(balance, "cash")
    equity = _line(balance, "equity")
    total_assets = _line(balance, "total_assets")
    current_assets = _line(balance, "current_assets")
    current_liabilities = _line(balance, "current_liabilities")
    inventory = _line(balance, "inventory") or 0.0
    fcf = _clean(info.get("freeCashflow"))

    def div(a, b):
        if a is None or b in (None, 0):
            return None
        return a / b

    # Bloque 1
    per = _clean(info.get("trailingPE"))
    growth = _clean(info.get("earningsGrowth"))
    peg = _clean(info.get("trailingPegRatio"))
    if peg is None and per and growth and growth > 0:
        peg = per / (growth * 100.0)

    # Bloque 2 — EV = market cap + deuda − caja
    ev = _clean(info.get("enterpriseValue"))
    if ev is None and market_cap is not None:
        ev = market_cap + (total_debt or 0.0) - (cash or 0.0)

    # Bloque 3
    tax_rate = None
    if tax is not None and pretax not in (None, 0):
        tax_rate = max(0.0, min(0.5, tax / pretax))
    nopat = ebit * (1 - (tax_rate if tax_rate is not None else 0.21)) if ebit is not None else None
    invested_capital = None
    if equity is not None:
        invested_capital = equity + (total_debt or 0.0)

    # Bloque 4
    net_debt_to_ebitda = None
    if total_debt is not None and ebitda not in (None, 0):
        net_debt_to_ebitda = (total_debt - (cash or 0.0)) / ebitda
    interest_coverage = None
    if ebit is not None and interest not in (None, 0):
        interest_coverage = ebit / abs(interest)

    # Bloque 5
    dcf = compute_dcf(info, financials, price)

    return {
        "price_used": price,
        # Bloque 1
        "per": per,
        "forward_per": _clean(info.get("forwardPE")),
        "peg": peg,
        "price_to_book": _clean(info.get("priceToBook")),
        "price_to_sales": _clean(info.get("priceToSalesTrailing12Months")),
        "dividend_yield": _normalize_dividend_yield(info.get("dividendYield")),
        "fcf_yield": div(fcf, market_cap),
        # Bloque 2
        "enterprise_value": ev,
        "ev_ebitda": _clean(info.get("enterpriseToEbitda")) or div(ev, ebitda),
        "ev_ebit": div(ev, ebit),
        "ev_fcf": div(ev, fcf),
        "ev_sales": _clean(info.get("enterpriseToRevenue")) or div(ev, revenue),
        # Bloque 3
        "roe": _clean(info.get("returnOnEquity")) or div(net_income, equity),
        "roa": _clean(info.get("returnOnAssets")) or div(net_income, total_assets),
        "roic": div(nopat, invested_capital),
        "gross_margin": _clean(info.get("grossMargins")) or div(gross_profit, revenue),
        "operating_margin": _clean(info.get("operatingMargins")) or div(ebit, revenue),
        "net_margin": _clean(info.get("profitMargins")) or div(net_income, revenue),
        # Bloque 4
        "current_ratio": _clean(info.get("currentRatio")) or div(current_assets, current_liabilities),
        "quick_ratio": _clean(info.get("quickRatio"))
        or div((current_assets - inventory) if current_assets is not None else None, current_liabilities),
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "interest_coverage": interest_coverage,
        "debt_to_equity": _normalize_debt_to_equity(info.get("debtToEquity")),
        # Bloque 5
        "wacc": dcf["wacc"],
        "dcf_fair_value": dcf["fair_value"],
        "dcf_upside": dcf["upside"],
        "dcf_assumptions": dcf["assumptions"],
    }


def fundamental_score(r: dict) -> float:
    """Score fundamental 0-100 determinista para la capa mecánica (5.1).

    Umbrales tomados de la sección 4.3 (ROE>15%, current ratio>1,
    deuda neta/EBITDA>3-4 peligroso, cobertura<2 crítica, PEG<1 barato...).
    Cubierto por test de regresión (16.6).
    """
    score = 50.0

    roe = r.get("roe")
    if roe is not None:
        score += 8 if roe > 0.15 else (-8 if roe < 0 else 0)

    net_margin = r.get("net_margin")
    if net_margin is not None:
        score += 5 if net_margin > 0.10 else (-8 if net_margin < 0 else 0)

    current_ratio = r.get("current_ratio")
    if current_ratio is not None:
        score += 4 if current_ratio > 1.0 else -6

    nd_ebitda = r.get("net_debt_to_ebitda")
    if nd_ebitda is not None:
        score += 5 if nd_ebitda < 3.0 else (-8 if nd_ebitda > 4.0 else 0)

    coverage = r.get("interest_coverage")
    if coverage is not None:
        score += 4 if coverage > 4.0 else (-8 if coverage < 2.0 else 0)

    per = r.get("per")
    if per is None or per < 0:
        score -= 4
    elif per < 15:
        score += 8
    elif per < 25:
        score += 4
    elif per > 40:
        score -= 6

    peg = r.get("peg")
    if peg is not None and peg > 0:
        score += 6 if peg < 1.0 else (2 if peg < 2.0 else -4)

    fcf_yield = r.get("fcf_yield")
    if fcf_yield is not None:
        if fcf_yield > 0.05:
            score += 6
        elif fcf_yield > 0.02:
            score += 3
        elif fcf_yield < 0:
            score -= 6

    upside = r.get("dcf_upside")
    if upside is not None:
        if upside > 0.20:
            score += 8
        elif upside > 0:
            score += 4
        elif upside < -0.20:
            score -= 8
        else:
            score -= 4

    return round(max(0.0, min(100.0, score)), 1)


def sync_fundamentals(asset: Asset) -> FundamentalRatios | None:
    """Pipeline completo: extrae info + estados, persiste crudos y ratios."""
    if asset.asset_type == AssetType.CRYPTO:
        # Sección 12: cripto no tiene estados contables; el scoring aplica
        # reglas más estrictas ante la ausencia de fundamentos.
        logger.info("Se omite fundamentales para cripto %s", asset.ticker)
        return None

    provider = get_provider()
    info = provider.get_info(asset.ticker) or {}
    financials = provider.get_financials(asset.ticker) or {}

    persist_statements(asset, financials)
    ratios = compute_ratios(asset, info, financials)
    score = fundamental_score(ratios)

    return FundamentalRatios.objects.create(
        asset=asset,
        as_of=timezone.now(),
        fundamental_score=score,
        **ratios,
    )


def latest_ratios(asset: Asset) -> FundamentalRatios | None:
    return asset.fundamental_ratios.order_by("-as_of").first()
