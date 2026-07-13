"""Endpoints de simulación y backtesting.

El router se monta con ``auth=django_auth`` (config/api.py): lo persistido
queda a nombre de ``request.user`` y solo puede colgarse de carteras propias.
"""
from django.shortcuts import get_object_or_404
from ninja import Router

from market.models import Asset
from market.services import load_price_frame
from portfolio.models import Portfolio

from .models import BacktestRun, Simulation
from .schemas import BacktestIn, BacktestOut, MessageOut, SimulationIn, SimulationOut
from .services import backtest_sma_cross, simulate_investment

router = Router()


@router.post("/run", response=SimulationOut)
def run_simulation(request, payload: SimulationIn):
    result = simulate_investment(
        initial_capital=payload.initial_capital,
        monthly_contribution=payload.monthly_contribution,
        years=payload.years,
        expected_return=payload.expected_return,
        volatility=payload.volatility,
    )
    simulation_id = None
    if payload.persist:
        portfolio = None
        if payload.portfolio_id is not None:
            portfolio = get_object_or_404(
                Portfolio, id=payload.portfolio_id, user=request.user
            )
        asset = (
            Asset.objects.filter(ticker__iexact=payload.ticker).first()
            if payload.ticker else None
        )
        sim = Simulation.objects.create(
            user=request.user,
            asset=asset,
            portfolio=portfolio,
            scenario_name=payload.scenario_name,
            initial_capital=payload.initial_capital,
            monthly_contribution=payload.monthly_contribution,
            time_horizon_years=payload.years,
            expected_return=payload.expected_return,
            volatility=payload.volatility,
            final_estimated_value=result["scenarios"]["medio"]["final_value"],
            optimistic_value=result["scenarios"]["optimista"]["final_value"],
            pessimistic_value=result["scenarios"]["pesimista"]["final_value"],
            total_contributed=result["total_contributed"],
            results=result,
        )
        simulation_id = sim.id
    return {**result, "simulation_id": simulation_id}


@router.post("/backtest", response={200: BacktestOut, 400: MessageOut})
def run_backtest(request, payload: BacktestIn):
    asset = get_object_or_404(Asset, ticker__iexact=payload.ticker)
    df = load_price_frame(asset)
    try:
        result = backtest_sma_cross(
            df,
            fast=payload.fast,
            slow=payload.slow,
            initial_capital=payload.initial_capital,
        )
    except ValueError as exc:
        return 400, {"detail": str(exc)}

    backtest_id = None
    if payload.persist:
        run = BacktestRun.objects.create(
            user=request.user,
            asset=asset,
            strategy=result["strategy"],
            params=result["params"],
            start_date=result["start_date"],
            end_date=result["end_date"],
            initial_capital=result["initial_capital"],
            final_value=result["final_value"],
            total_return_pct=result["total_return_pct"],
            cagr_pct=result["cagr_pct"],
            volatility_pct=result["volatility_pct"],
            max_drawdown_pct=result["max_drawdown_pct"],
            win_rate_pct=result["win_rate_pct"],
            sharpe_ratio=result["sharpe_ratio"],
            profit_factor=result["profit_factor"] if isinstance(result["profit_factor"], (int, float)) else None,
            num_trades=result["num_trades"],
            equity_curve=result["equity_curve"],
        )
        backtest_id = run.id
    return 200, {**result, "backtest_id": backtest_id}
