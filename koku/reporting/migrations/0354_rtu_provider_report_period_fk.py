# Wire rates_to_usage source_uuid and report_period_id as FKs (GAP-4, data retention).
import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0353_rtu_fk_cascade"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="ratestousage",
            name="ratestousage_start_src_rp_idx",
        ),
        migrations.RenameField(
            model_name="ratestousage",
            old_name="report_period_id",
            new_name="report_period",
        ),
        migrations.AlterField(
            model_name="ratestousage",
            name="report_period",
            field=models.ForeignKey(
                db_column="report_period_id",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="reporting.ocpusagereportperiod",
            ),
        ),
        migrations.AlterField(
            model_name="ratestousage",
            name="source_uuid",
            field=models.ForeignKey(
                db_column="source_uuid",
                on_delete=django.db.models.deletion.CASCADE,
                to="reporting.tenantapiprovider",
            ),
        ),
        migrations.AddIndex(
            model_name="ratestousage",
            index=models.Index(
                fields=["usage_start", "source_uuid", "report_period"],
                name="ratestousage_start_src_rp_idx",
            ),
        ),
    ]
