from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

# Trigram indexes exist to fix the O(n) Python fuzzy-match scan in
# apps/medicines/services/search.py at catalog scale. They are PostgreSQL-only
# (pg_trgm has no SQLite equivalent) and every operation below no-ops cleanly
# on any other backend, so this migration is safe to run against the shared
# sqlite dev database (see repo CLAUDE.md) as well as the Postgres deployment.
#
# TrigramExtension() itself already no-ops on non-Postgres connections; the
# index creation below is guarded explicitly for the same reason and to keep
# the SQL out of Django's cross-backend schema editor entirely.

INDEXES = [
    ("medicines_medicine_brand_name_trgm", "medicines_medicine", "brand_name"),
    ("medicines_medicine_generic_name_trgm", "medicines_medicine", "generic_name"),
    ("medicines_medicinealias_alias_trgm", "medicines_medicinealias", "alias"),
]


def create_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for index_name, table, column in INDEXES:
        schema_editor.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table} USING gin ({column} gin_trgm_ops)')


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for index_name, _table, _column in INDEXES:
        schema_editor.execute(f"DROP INDEX IF EXISTS {index_name}")


class Migration(migrations.Migration):

    dependencies = [
        ("medicines", "0007_alias_transliteration_type"),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
