from django.contrib import admin

from .models import BacktestRun, Simulation


@admin.register(Simulation)
class SimulationAdmin(admin.ModelAdmin):
    list_display = (
        "scenario_name", "asset", "portfolio", "initial_capital",
        "monthly_contribution", "time_horizon_years",
        "final_estimated_value", "created_at",
    )
    list_filter = ("asset",)


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = (
        "asset", "strategy", "total_return_pct", "cagr_pct",
        "max_drawdown_pct", "sharpe_ratio", "num_trades", "created_at",
    )
    list_filter = ("strategy", "asset")
