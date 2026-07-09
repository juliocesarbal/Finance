"""Ingesta manual de noticias (yfinance + Google News RSS)."""
from django.core.management.base import BaseCommand

from market.models import Asset
from news.services import ingest_asset_news, ingest_rss_for_query


class Command(BaseCommand):
    help = "Ingesta noticias corporativas y sectoriales para los activos."

    def add_arguments(self, parser):
        parser.add_argument("--tickers", type=str, default="")
        parser.add_argument("--skip-rss", action="store_true")

    def handle(self, *args, **options):
        qs = Asset.objects.filter(is_active=True)
        if options["tickers"]:
            tickers = [t.strip().upper() for t in options["tickers"].split(",")]
            qs = qs.filter(ticker__in=tickers)

        total = 0
        for asset in qs:
            created = ingest_asset_news(asset)
            if not options["skip_rss"]:
                query = f'"{asset.name}" stock' if asset.name else f"{asset.ticker} stock"
                created += ingest_rss_for_query(query, asset=asset)
            total += created
            self.stdout.write(f"{asset.ticker}: {created} noticias nuevas")
        self.stdout.write(self.style.SUCCESS(f"Total: {total} noticias nuevas."))
