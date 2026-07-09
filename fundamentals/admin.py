from django.contrib import admin

from .models import FinancialStatement, FundamentalRatios


@admin.register(FinancialStatement)
class FinancialStatementAdmin(admin.ModelAdmin):
    list_display = ("asset", "statement_type", "period_ending", "created_at")
    list_filter = ("statement_type", "asset")


@admin.register(FundamentalRatios)
class FundamentalRatiosAdmin(admin.ModelAdmin):
    list_display = (
        "asset", "as_of", "per", "peg", "roe", "net_margin",
        "net_debt_to_ebitda", "dcf_fair_value", "dcf_upside", "fundamental_score",
    )
    list_filter = ("asset",)
