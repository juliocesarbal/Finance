"""Ingesta manual de precios históricos e indicadores."""
from django.core.management.base import BaseCommand

from market.models import Asset
from market.services import compute_and_store_indicators, ingest_prices


class Command(BaseCommand):
    help = "Descarga histórico de precios (yfinance con caché) y calcula indicadores."

    def add_arguments(self, parser):
        parser.add_argument("--tickers", type=str, default="", help="Lista separada por comas; vacío = todos los activos.")
        parser.add_argument("--period", type=str, default="1y", help="Período yfinance (1mo, 6mo, 1y, 2y, 5y, max).")
        parser.add_argument("--skip-indicators", action="store_true")

    def handle(self, *args, **options):
        qs = Asset.objects.filter(is_active=True)
        if options["tickers"]:
            tickers = [t.strip().upper() for t in options["tickers"].split(",")]
            qs = qs.filter(ticker__in=tickers)

        for asset in qs:
            try:
                n = ingest_prices(asset, period=options["period"])
                msg = f"{asset.ticker}: {n} barras"
                if not options["skip_indicators"]:
                    k = compute_and_store_indicators(asset)
                    msg += f", {k} filas de indicadores"
                self.stdout.write(msg)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"{asset.ticker}: ERROR {exc}"))
        self.stdout.write(self.style.SUCCESS("Ingesta terminada."))
