from datetime import date, datetime

from ninja import Schema


class RatiosOut(Schema):
    ticker: str
    as_of: datetime
    price_used: float | None = None

    # Bloque 1 — múltiplos de precio
    per: float | None = None
    forward_per: float | None = None
    peg: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    dividend_yield: float | None = None
    fcf_yield: float | None = None

    # Bloque 2 — enterprise value
    enterprise_value: float | None = None
    ev_ebitda: float | None = None
    ev_ebit: float | None = None
    ev_fcf: float | None = None
    ev_sales: float | None = None

    # Bloque 3 — rentabilidad
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None

    # Bloque 4 — liquidez y solvencia
    current_ratio: float | None = None
    quick_ratio: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    debt_to_equity: float | None = None

    # Bloque 5 — valoración intrínseca
    wacc: float | None = None
    dcf_fair_value: float | None = None
    dcf_upside: float | None = None
    dcf_assumptions: dict

    fundamental_score: float | None = None

    @staticmethod
    def resolve_ticker(obj):
        return obj.asset.ticker


class StatementOut(Schema):
    statement_type: str
    period_ending: date
    data: dict


class MessageOut(Schema):
    detail: str
