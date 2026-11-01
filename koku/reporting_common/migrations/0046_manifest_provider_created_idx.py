from django.db import migrations
from django.db import models

INDEX_NAME = "manifest_provider_created_idx"


def drop_invalid_index(apps, schema_editor):
    """Drop a leftover INVALID index from an interrupted concurrent build.

    An interrupted CREATE INDEX CONCURRENTLY leaves an invalid index behind, which
    CREATE INDEX ... IF NOT EXISTS would skip; dropping it lets the retry rebuild it.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
              FROM pg_index i
              JOIN pg_class c ON c.oid = i.indexrelid
             WHERE c.relname = %s
               AND c.relnamespace = current_schema()::regnamespace
               AND NOT i.indisvalid
            """,
            [INDEX_NAME],
        )
        if cursor.fetchone():
            cursor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};")


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    atomic = False

    dependencies = [
        ("reporting_common", "0045_ingressdeadletterqueue"),
    ]

    # RunPython/RunSQL (not AddIndexConcurrently): tenant schema creation runs all migrations
    # inside a transaction, and AddIndexConcurrently rejects that before the router skips this
    # shared app's operation. RunPython and RunSQL consult the router first.
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="costusagereportmanifest",
                    index=models.Index(fields=["provider", "-creation_datetime"], name=INDEX_NAME),
                ),
            ],
            database_operations=[
                migrations.RunPython(drop_invalid_index, migrations.RunPython.noop),
                migrations.RunSQL(
                    sql=(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                        "ON reporting_common_costusagereportmanifest (provider_id, creation_datetime DESC);"
                    ),
                    reverse_sql=f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME};",
                ),
            ],
        ),
    ]
