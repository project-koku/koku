from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    atomic = False

    dependencies = [
        ("reporting_common", "0045_ingressdeadletterqueue"),
    ]

    # RunSQL (not AddIndexConcurrently): tenant schema creation runs all migrations inside
    # a transaction, and AddIndexConcurrently rejects that before the router skips this
    # shared app's operation. RunSQL consults the router first.
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddIndex(
                    model_name="costusagereportmanifest",
                    index=models.Index(fields=["provider", "-creation_datetime"], name="manifest_provider_created_idx"),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS manifest_provider_created_idx "
                        "ON reporting_common_costusagereportmanifest (provider_id, creation_datetime DESC);"
                    ),
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS manifest_provider_created_idx;",
                ),
            ],
        ),
    ]
