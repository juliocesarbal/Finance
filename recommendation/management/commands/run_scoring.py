"""Corre el pipeline de dos etapas (5.3) manualmente."""
from django.core.management.base import BaseCommand

from recommendation.pipeline import run_universe_scoring


class Command(BaseCommand):
    help = "Etapa 1: score mecánico sobre el universo. Con --escalate corre también el agente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--escalate", action="store_true",
            help="Escala el top N al agente de verificación (requiere ANTHROPIC_API_KEY).",
        )
        parser.add_argument(
            "--async-agent", action="store_true",
            help="Encola el agente vía Celery en lugar de correrlo en este proceso.",
        )

    def handle(self, *args, **options):
        result = run_universe_scoring(
            escalate=options["escalate"],
            sync_agent=not options["async_agent"],
        )
        self.stdout.write(f"Activos puntuados: {result['scored']} (errores: {result['errors']})")
        self.stdout.write("Ranking mecánico:")
        for row in result["ranking"]:
            self.stdout.write(f"  {row['ticker']:>10}  {row['score']:>5}  {row['signal']}")
        if result["escalated"]:
            self.stdout.write(self.style.SUCCESS(f"Escalados al agente: {', '.join(result['escalated'])}"))
        self.stdout.write(self.style.SUCCESS("Scoring terminado."))
