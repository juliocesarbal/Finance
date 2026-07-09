"""Crea los activos de la watchlist inicial (sección 4.1)."""
from django.conf import settings
from django.core.management.base import BaseCommand

from market.models import Asset
from market.services import sync_asset_metadata


class Command(BaseCommand):
    help = "Crea los activos de settings.WATCHLIST y sincroniza sus metadatos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-network",
            action="store_true",
            help="No consultar yfinance para metadatos (solo crear tickers).",
        )

    def handle(self, *args, **options):
        created_count = 0
        for ticker in settings.WATCHLIST:
            asset, created = Asset.objects.get_or_create(ticker=ticker.upper())
            if created:
                created_count += 1
            if not options["no_network"]:
                sync_asset_metadata(asset)
                self.stdout.write(f"  {asset.ticker}: {asset.name or '(sin nombre)'} [{asset.asset_type}]")
        self.stdout.write(
            self.style.SUCCESS(
                f"Watchlist lista: {created_count} activos nuevos, "
                f"{Asset.objects.count()} en total."
            )
        )
