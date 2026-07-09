"""Cálculo manual de métricas de riesgo."""
from django.core.management.base import BaseCommand

from market.models import Asset
from risk.services import compute_asset_risk


class Command(BaseCommand):
    help = "Calcula volatilidad, drawdown, beta y correlaciones por activo (4.8)."

    def add_arguments(self, parser):
        parser.add_argument("--tickers", type=str, default="")

    def handle(self, *args, **options):
        qs = Asset.objects.filter(is_active=True)
        if options["tickers"]:
            tickers = [t.strip().upper() for t in options["tickers"].split(",")]
            qs = qs.filter(ticker__in=tickers)

        for asset in qs:
            try:
                r = compute_asset_risk(asset)
                self.stdout.write(
                    f"{asset.ticker}: score={r['risk_score']} vol={r['volatility_annual']} "
                    f"dd={r['max_drawdown']} beta={r['beta']}"
                )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"{asset.ticker}: ERROR {exc}"))
        self.stdout.write(self.style.SUCCESS("Riesgo calculado."))
