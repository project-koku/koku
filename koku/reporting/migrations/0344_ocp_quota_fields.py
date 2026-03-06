#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import uuid

import django.db.models.deletion
from django.db import migrations
from django.db import models


def set_pg_extended_mode(apps, schema_editor):
    schema_editor.execute("SET LOCAL jit = off;")
    schema_editor.execute("SET LOCAL max_parallel_workers_per_gather = 0;")


def unset_pg_extended_mode(apps, schema_editor):
    schema_editor.execute("RESET jit;")
    schema_editor.execute("RESET max_parallel_workers_per_gather;")


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0343_ocp_line_item_models"),
    ]

    operations = [
        # 1 -- New columns on daily summary (no extended mode needed -- ADD COLUMN NULL is instant)
        migrations.AddField(
            model_name="ocpusagelineitemdailysummary",
            name="quota_name",
            field=models.CharField(max_length=253, null=True),
        ),
        migrations.AddField(
            model_name="ocpusagelineitemdailysummary",
            name="quota_type",
            field=models.CharField(max_length=10, null=True),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(fields=["quota_name"], name="summary_quota_name_idx"),
        ),
        # 2 -- New columns on self-hosted staging table
        migrations.AddField(
            model_name="ocpusagelineitemdailysummarystaging",
            name="quota_name",
            field=models.CharField(max_length=253, null=True),
        ),
        migrations.AddField(
            model_name="ocpusagelineitemdailysummarystaging",
            name="quota_type",
            field=models.CharField(max_length=10, null=True),
        ),
        # 3 -- New quota labels line item tables (extended mode for new table creation)
        migrations.RunPython(set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
        migrations.CreateModel(
            name="OCPQuotaLabelsLineItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("report_period_start", models.DateTimeField(null=True)),
                ("report_period_end", models.DateTimeField(null=True)),
                ("interval_start", models.DateTimeField(db_index=True, null=True)),
                ("interval_end", models.DateTimeField(null=True)),
                ("usage_start", models.DateField(db_index=True, null=True)),
                ("source", models.CharField(db_index=True, max_length=64, null=True)),
                ("year", models.CharField(max_length=4, null=True)),
                ("month", models.CharField(max_length=2, null=True)),
                ("manifestid", models.CharField(max_length=256, null=True)),
                ("reportnumhours", models.IntegerField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("quota_name", models.CharField(max_length=253, null=True)),
                ("quota_type", models.CharField(max_length=10, null=True)),
            ],
            options={"db_table": "openshift_quota_labels_line_items", "managed": True},
        ),
        migrations.AddIndex(
            model_name="ocpquotalabelslineitem",
            index=models.Index(fields=["source", "year", "month"], name="ocp_quota_lbl_src_yr_mo_idx"),
        ),
        migrations.CreateModel(
            name="OCPQuotaLabelsLineItemDaily",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("report_period_start", models.DateTimeField(null=True)),
                ("report_period_end", models.DateTimeField(null=True)),
                ("interval_start", models.DateTimeField(db_index=True, null=True)),
                ("interval_end", models.DateTimeField(null=True)),
                ("usage_start", models.DateField(db_index=True, null=True)),
                ("source", models.CharField(db_index=True, max_length=64, null=True)),
                ("year", models.CharField(max_length=4, null=True)),
                ("month", models.CharField(max_length=2, null=True)),
                ("manifestid", models.CharField(max_length=256, null=True)),
                ("reportnumhours", models.IntegerField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("quota_name", models.CharField(max_length=253, null=True)),
                ("quota_type", models.CharField(max_length=10, null=True)),
            ],
            options={"db_table": "openshift_quota_labels_line_items_daily", "managed": True},
        ),
        migrations.AddIndex(
            model_name="ocpquotalabelslineitemdaily",
            index=models.Index(fields=["source", "year", "month"], name="ocp_quota_lbl_dy_src_yr_mo_idx"),
        ),
        # 4 -- New partitioned UI summary table
        migrations.CreateModel(
            name="OCPCostSummaryByQuotaP",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("quota_name", models.CharField(max_length=253, null=True)),
                ("quota_type", models.CharField(max_length=10, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("infrastructure_raw_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("infrastructure_markup_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_cpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_memory_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_volume_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_rate_type", models.TextField(null=True)),
                ("distributed_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("raw_currency", models.TextField(null=True)),
                (
                    "source_uuid",
                    models.ForeignKey(
                        db_column="source_uuid",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocp_cost_summary_by_quota_p", "managed": True},
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybyquotap",
            index=models.Index(fields=["usage_start"], name="ocp_cost_quota_ustart_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybyquotap",
            index=models.Index(fields=["quota_name"], name="ocp_cost_quota_name_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybyquotap",
            index=models.Index(fields=["quota_type"], name="ocp_cost_quota_type_idx"),
        ),
        migrations.RunPython(unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
    ]
