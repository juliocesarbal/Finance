from django.contrib import admin

from .models import Asset, MarketPrice, TechnicalIndicator


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = (
        "ticker", "name", "asset_type", "sector", "country", "currency", "is_active",
    )
    list_filter = ("asset_type", "sector", "country", "is_active")
    search_fields = ("ticker", "name")


@admin.register(MarketPrice)
class MarketPriceAdmin(admin.ModelAdmin):
    list_display = ("asset", "datetime", "open", "high", "low", "close", "volume")
    list_filter = ("asset",)
    date_hierarchy = "datetime"


@admin.register(TechnicalIndicator)
class TechnicalIndicatorAdmin(admin.ModelAdmin):
    list_display = ("asset", "datetime", "sma_20", "sma_50", "sma_200", "rsi", "macd")
    list_filter = ("asset",)
    date_hierarchy = "datetime"
