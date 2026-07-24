# State-only migration for rates_to_usage schema improvements.
#
# The original DDL (TRUNCATE, indexes, CASCADE FKs) was moved to 0353.
# The design of that DDL expects no workers actively inserting into the RTU
# table. We missed a rogue insert and the fix (943aaa4) lands after this
# migration was added to git history. Due to automatic stage releases the
# original migration ran on Stage, but not in Prod.
#
# 0352 keeps Django project state in sync with RatesToUsage (so
# makemigrations stays clean) without touching the database. 0353 applies
# the real DDL after the rogue-insert fix is live.
import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0351_create_ocp_cost_breakdown_p"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddIndex(
                    model_name="ratestousage",
                    index=models.Index(fields=["rate_id"], name="ratestousage_rate_id_idx"),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddIndex(
                    model_name="ratestousage",
                    index=models.Index(fields=["cost_model_id"], name="ratestousage_cost_model_id_idx"),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="rate",
                    field=models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="cost_models.rate",
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="cost_model",
                    field=models.ForeignKey(
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="cost_models.costmodel",
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="ratestousage",
                    name="ratestousage_start_src_rp_idx",
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RenameField(
                    model_name="ratestousage",
                    old_name="report_period_id",
                    new_name="report_period",
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
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
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="ratestousage",
                    name="source_uuid",
                    field=models.ForeignKey(
                        db_column="source_uuid",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddIndex(
                    model_name="ratestousage",
                    index=models.Index(
                        fields=["usage_start", "source_uuid", "report_period"],
                        name="ratestousage_start_src_rp_idx",
                    ),
                ),
            ],
        ),
    ]
