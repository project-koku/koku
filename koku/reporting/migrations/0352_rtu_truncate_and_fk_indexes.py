# Truncate rates_to_usage and add indexes on rate_id and cost_model_id (GAP-5).
# Prerequisite: smart revert (#6172) deployed and RTU Unleash flag OFF.
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0351_create_ocp_cost_breakdown_p"),
    ]

    operations = [
        migrations.RunSQL(
            sql="TRUNCATE TABLE rates_to_usage;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(fields=["rate_id"], name="ratestousage_rate_id_idx"),
        ),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(fields=["cost_model_id"], name="ratestousage_cost_model_id_idx"),
        ),
    ]
