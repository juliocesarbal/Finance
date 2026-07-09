"""Escaneo manual del motor de descubrimiento."""
from django.core.management.base import BaseCommand

from discovery.services import run_discovery


class Command(BaseCommand):
    help = "Escanea los temas emergentes vía Google News RSS y genera reportes (secciones 6/13/14)."

    def handle(self, *args, **options):
        result = run_discovery()
        self.stdout.write(f"Temas escaneados: {result['scanned']} (errores: {result['errors']})")
        for row in result["reports"]:
            self.stdout.write(f"  {row['score']:>5}  [{row['risk_level']:>9}]  {row['topic']}")
        self.stdout.write(self.style.SUCCESS("Descubrimiento terminado."))
