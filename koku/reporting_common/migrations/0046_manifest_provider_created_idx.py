from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    atomic = False

    dependencies = [
        ("reporting_common", "0045_ingressdeadletterqueue"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="costusagereportmanifest",
            index=models.Index(fields=["provider", "-creation_datetime"], name="manifest_provider_created_idx"),
        ),
    ]
