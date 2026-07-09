from ninja import Schema


class SimulationIn(Schema):
    initial_capital: float
    monthly_contribution: float = 0.0
    years: float
    expected_return: float = 0.08
    volatility: float = 0.15
    scenario_name: str = "escenario base"
    ticker: str | None = None
    portfolio_id: int | None = None
    persist: bool = True


class ScenarioOut(Schema):
    annual_return_used: float
    final_value: float
    gain: float
    cumulative_return_pct: float
    approx_annualized_return_pct: float | None = None


class SimulationOut(Schema):
    initial_capital: float
    monthly_contribution: float
    years: float
    expected_return: float
    volatility: float
    total_contributed: float
    scenarios: dict[str, ScenarioOut]
    disclaimer: str
    simulation_id: int | None = None


class BacktestIn(Schema):
    ticker: str
    fast: int = 50
    slow: int = 200
    initial_capital: float = 10000.0
    persist: bool = True


class BacktestOut(Schema):
    strategy: str
    params: dict
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    cagr_pct: float
    volatility_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    sharpe_ratio: float
    profit_factor: float | None = None
    num_trades: int
    equity_curve: list
    disclaimer: str
    backtest_id: int | None = None


class MessageOut(Schema):
    detail: str
