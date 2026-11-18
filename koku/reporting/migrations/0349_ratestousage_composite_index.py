# Replace (usage_start, source_uuid) + (report_period_id) separate indexes
# with a single composite (usage_start, source_uuid, report_period_id) index
# that covers both the DELETE and SELECT WHERE clauses in the RTU SQL pipeline.
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0348_create_rates_to_usage"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="ratestousage",
            name="ratestousage_start_source_idx",
        ),
        migrations.RemoveIndex(
            model_name="ratestousage",
            name="ratestousage_report_period_idx",
        ),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(
                fields=["usage_start", "source_uuid", "report_period_id"],
                name="ratestousage_start_src_rp_idx",
            ),
        ),
    ]
