# COST-7249 Phase 4: Create reporting_ocp_cost_breakdown_p partitioned table
import uuid

import django.db.models.deletion
from django.db import migrations
from django.db import models

from koku.database import set_pg_extended_mode
from koku.database import unset_pg_extended_mode


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0350_widen_ratestousage_label_hash"),
    ]

    operations = [
        migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
        migrations.CreateModel(
            name="OCPCostUIBreakDownP",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("custom_name", models.CharField(max_length=50)),
                ("metric_type", models.CharField(max_length=30)),
                ("cost_model_rate_type", models.TextField(null=True)),
                (
                    "cost_value",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("raw_currency", models.TextField(null=True)),
                ("path", models.CharField(max_length=512)),
                ("depth", models.SmallIntegerField()),
                ("parent_path", models.CharField(max_length=512)),
                ("top_category", models.CharField(max_length=512)),
                ("breakdown_category", models.CharField(max_length=50)),
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
                (
                    "source_uuid",
                    models.ForeignKey(
                        db_column="source_uuid",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
            options={
                "db_table": "reporting_ocp_cost_breakdown_p",
                "indexes": [
                    models.Index(
                        fields=["usage_start"],
                        name="ocpcostbreakdown_usage_start",
                    ),
                    models.Index(
                        fields=["namespace"],
                        name="ocpcostbreakdown_namespace",
                    ),
                    models.Index(
                        fields=["cluster_id"],
                        name="ocpcostbreakdown_cluster_id",
                    ),
                    models.Index(
                        fields=["custom_name"],
                        name="ocpcostbreakdown_custom_name",
                    ),
                    models.Index(
                        fields=["path"],
                        name="ocpcostbreakdown_path",
                    ),
                    models.Index(
                        fields=["depth"],
                        name="ocpcostbreakdown_depth",
                    ),
                    models.Index(
                        fields=["top_category"],
                        name="ocpcostbreakdown_top_category",
                    ),
                    models.Index(
                        fields=["usage_start", "source_uuid"],
                        name="ocpcostbreakdown_start_src_idx",
                    ),
                    models.Index(
                        fields=["node"],
                        name="ocpcostbreakdown_node_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
    ]
