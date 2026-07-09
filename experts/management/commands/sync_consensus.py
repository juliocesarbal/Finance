"""Sincronización manual del consenso de analistas."""
from django.core.management.base import BaseCommand

from experts.services import sync_consensus
from market.models import Asset, AssetType


class Command(BaseCommand):
    help = "Sincroniza el consenso de analistas (recomendaciones + precios objetivo)."

    def add_arguments(self, parser):
        parser.add_argument("--tickers", type=str, default="")

    def handle(self, *args, **options):
        qs = Asset.objects.filter(is_active=True).exclude(asset_type=AssetType.CRYPTO)
        if options["tickers"]:
            tickers = [t.strip().upper() for t in options["tickers"].split(",")]
            qs = qs.filter(ticker__in=tickers)

        for asset in qs:
            c = sync_consensus(asset)
            if c:
                self.stdout.write(
                    f"{asset.ticker}: {c.total_analysts} analistas, rating {c.rating_mean}, "
                    f"objetivo {c.mean_target} (dispersión {c.dispersion}) {c.change_alert}"
                )
            else:
                self.stdout.write(f"{asset.ticker}: sin datos")
        self.stdout.write(self.style.SUCCESS("Consenso sincronizado."))
