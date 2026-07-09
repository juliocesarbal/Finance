"""Modelos del monitor de mercado (secciones 4.1, 4.2 y 15.1–15.3)."""
from django.db import models

from core.models import TimeStampedModel


class AssetType(models.TextChoices):
    STOCK = "stock", "Acción"
    INDEX = "index", "Índice"
    ETF = "etf", "ETF"
    CRYPTO = "crypto", "Criptomoneda"
    BOND = "bond", "Bono / renta fija"
    COMMODITY = "commodity", "Commodity"


class Asset(TimeStampedModel):
    """Activo financiero (15.1)."""

    ticker = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200, blank=True)
    asset_type = models.CharField(
        max_length=20, choices=AssetType.choices, default=AssetType.STOCK
    )
    sector = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    exchange = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["ticker"]

    def __str__(self):
        return self.ticker


class MarketPrice(models.Model):
    """Barra OHLCV diaria (15.2). Candidata a hypertable de TimescaleDB:
    la migración la convierte solo si la extensión está disponible.
    Los datos intradía se sirven en vivo desde la caché del provider,
    no se persisten."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="prices")
    datetime = models.DateTimeField(db_index=True)
    open = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    high = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    low = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    close = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    volume = models.BigIntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "datetime"], name="uniq_price_asset_datetime"
            ),
        ]
        indexes = [models.Index(fields=["asset", "-datetime"])]
        ordering = ["datetime"]

    def __str__(self):
        return f"{self.asset.ticker} {self.datetime:%Y-%m-%d} c={self.close}"


class TechnicalIndicator(models.Model):
    """Indicadores técnicos calculados con pandas (4.2, 15.3)."""

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="indicators"
    )
    datetime = models.DateTimeField(db_index=True)
    sma_20 = models.FloatField(null=True)
    sma_50 = models.FloatField(null=True)
    sma_200 = models.FloatField(null=True)
    rsi = models.FloatField(null=True)
    macd = models.FloatField(null=True)
    macd_signal = models.FloatField(null=True)
    macd_hist = models.FloatField(null=True)
    bb_upper = models.FloatField(null=True)
    bb_middle = models.FloatField(null=True)
    bb_lower = models.FloatField(null=True)
    volatility = models.FloatField(null=True)
    relative_volume = models.FloatField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "datetime"], name="uniq_indicator_asset_datetime"
            ),
        ]
        indexes = [models.Index(fields=["asset", "-datetime"])]
        ordering = ["datetime"]

    def __str__(self):
        return f"{self.asset.ticker} {self.datetime:%Y-%m-%d}"
