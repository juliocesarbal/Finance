"""Orquestador del flujo completo de una recomendación (sección 17).

Ejecuta en orden: precios → indicadores → noticias → fundamentales →
consenso → riesgo → scoring mecánico (+ escalado opcional al agente).
Equivale a lo que Celery Beat hace de forma periódica, en un solo comando.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Corre el pipeline completo de datos y scoring (sección 17 del documento)."

    def add_arguments(self, parser):
        parser.add_argument("--tickers", type=str, default="")
        parser.add_argument("--escalate", action="store_true", help="Corre también el agente 5.2 sobre el top N.")
        parser.add_argument("--skip-news", action="store_true")
        parser.add_argument("--skip-discovery", action="store_true")

    def handle(self, *args, **options):
        tickers = options["tickers"]

        self.stdout.write(self.style.MIGRATE_HEADING("1/7 Precios e indicadores (yfinance con caché)"))
        call_command("ingest_prices", tickers=tickers)

        if not options["skip_news"]:
            self.stdout.write(self.style.MIGRATE_HEADING("2/7 Noticias (yfinance .news + Google News RSS)"))
            call_command("ingest_news", tickers=tickers)
        else:
            self.stdout.write("2/7 Noticias: omitido")

        self.stdout.write(self.style.MIGRATE_HEADING("3/7 Fundamentales (5 bloques + DCF)"))
        call_command("sync_fundamentals", tickers=tickers)

        self.stdout.write(self.style.MIGRATE_HEADING("4/7 Consenso de analistas"))
        call_command("sync_consensus", tickers=tickers)

        self.stdout.write(self.style.MIGRATE_HEADING("5/7 Métricas de riesgo"))
        call_command("compute_risk", tickers=tickers)

        self.stdout.write(self.style.MIGRATE_HEADING("6/7 Scoring mecánico 5.1" + (" + agente 5.2" if options["escalate"] else "")))
        if options["escalate"]:
            call_command("run_scoring", "--escalate")
        else:
            call_command("run_scoring")

        if not options["skip_discovery"]:
            self.stdout.write(self.style.MIGRATE_HEADING("7/7 Descubrimiento de mercados emergentes"))
            call_command("run_discovery")
        else:
            self.stdout.write("7/7 Descubrimiento: omitido")

        self.stdout.write(self.style.SUCCESS("Pipeline completo terminado (sección 17)."))
