"""Sincronización manual de fundamentales."""
from django.core.management.base import BaseCommand

from fundamentals.services import sync_fundamentals
from market.models import Asset, AssetType


class Command(BaseCommand):
    help = "Extrae estados financieros y calcula los 5 bloques de ratios (4.3)."

    def add_arguments(self, parser):
        parser.add_argument("--tickers", type=str, default="")

    def handle(self, *args, **options):
        qs = Asset.objects.filter(is_active=True)
        if options["tickers"]:
            tickers = [t.strip().upper() for t in options["tickers"].split(",")]
            qs = qs.filter(ticker__in=tickers)

        for asset in qs:
            if asset.asset_type == AssetType.CRYPTO:
                self.stdout.write(f"{asset.ticker}: omitido (cripto, sección 12)")
                continue
            try:
                ratios = sync_fundamentals(asset)
                if ratios:
                    self.stdout.write(
                        f"{asset.ticker}: score fundamental {ratios.fundamental_score} "
                        f"(PER={ratios.per}, ROE={ratios.roe}, DCF upside={ratios.dcf_upside})"
                    )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"{asset.ticker}: ERROR {exc}"))
        self.stdout.write(self.style.SUCCESS("Fundamentales sincronizados."))
