"""Convierte MarketPrice y TechnicalIndicator en hypertables de TimescaleDB.

Condicional (sección 16.2): solo actúa si el motor es PostgreSQL y la
extensión timescaledb está disponible. En Railway (Postgres estándar) o en
SQLite (tests) es un no-op y las tablas quedan como relacionales normales,
que funcionan perfectamente.

Detalle técnico: TimescaleDB exige que todo índice único incluya la columna
de partición. Django crea la PK sobre `id`, así que se reemplaza por una PK
compuesta (id, datetime) — seguro porque ningún FK apunta a estas tablas.
"""
from django.db import migrations

HYPERTABLES = ["market_marketprice", "market_technicalindicator"]


def enable_hypertables(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"
        )
        if cursor.fetchone() is None:
            print(
                "\n  [market] TimescaleDB no disponible en este servidor: "
                "se usan tablas PostgreSQL estándar (funcional, sin hypertables)."
            )
            return

        cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        for table in HYPERTABLES:
            cursor.execute(
                "SELECT 1 FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = %s",
                [table],
            )
            if cursor.fetchone():
                continue
            cursor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT "{table}_pkey"')
            cursor.execute(f'ALTER TABLE "{table}" ADD PRIMARY KEY (id, datetime)')
            cursor.execute(
                f"SELECT create_hypertable('{table}', 'datetime', "
                "chunk_time_interval => INTERVAL '30 days', migrate_data => TRUE)"
            )
            print(f"\n  [market] {table} convertida en hypertable de TimescaleDB.")


def noop(apps, schema_editor):
    """Sin reversa: la hypertable sigue siendo una tabla válida."""


class Migration(migrations.Migration):
    dependencies = [
        ("market", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_hypertables, noop),
    ]
