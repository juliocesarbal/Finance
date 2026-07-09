from django.contrib import admin

from .models import Portfolio, PortfolioPosition


class PositionInline(admin.TabularInline):
    model = PortfolioPosition
    extra = 0
    raw_id_fields = ("asset",)


@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "base_currency", "created_at")
    inlines = [PositionInline]


@admin.register(PortfolioPosition)
class PortfolioPositionAdmin(admin.ModelAdmin):
    list_display = (
        "portfolio", "asset", "quantity", "average_price",
        "current_value", "weight", "profit_loss",
    )
    list_filter = ("portfolio",)
    raw_id_fields = ("asset",)
