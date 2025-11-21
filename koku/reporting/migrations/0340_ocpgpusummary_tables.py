# Generated manually for GPU UI summary tables
from django.db import migrations
from django.db import models

from koku.database import set_pg_extended_mode
from koku.database import unset_pg_extended_mode


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0339_ocpusagelineitemdailysummary_cost_model_gpu_cost"),
    ]

    operations = [
        migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
        # Create OCPGpuSummaryP table
        migrations.CreateModel(
            name="OCPGpuSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("pod", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("gpu_vendor_name", models.CharField(max_length=128, null=True)),
                ("gpu_model_name", models.CharField(max_length=128, null=True)),
                ("gpu_memory_capacity_mib", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("gpu_hours", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("gpu_count", models.IntegerField(null=True)),
                ("gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("unallocated_gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("raw_currency", models.TextField(null=True)),
                ("cost_model_cpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_memory_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_volume_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_rate_type", models.TextField(null=True)),
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True, on_delete=models.deletion.CASCADE, to="reporting.openshiftcostcategory"
                    ),
                ),
                (
                    "source_uuid",
                    models.ForeignKey(
                        db_column="source_uuid",
                        null=True,
                        on_delete=models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
            options={
                "db_table": "reporting_ocp_gpu_summary_p",
            },
        ),
        # Create OCPGpuSummaryByProjectP table
        migrations.CreateModel(
            name="OCPGpuSummaryByProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("gpu_vendor_name", models.CharField(max_length=128, null=True)),
                ("gpu_model_name", models.CharField(max_length=128, null=True)),
                ("gpu_memory_capacity_mib", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("gpu_hours", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("gpu_count", models.IntegerField(null=True)),
                ("gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("unallocated_gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("raw_currency", models.TextField(null=True)),
                ("cost_model_cpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_memory_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_volume_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_rate_type", models.TextField(null=True)),
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True, on_delete=models.deletion.CASCADE, to="reporting.openshiftcostcategory"
                    ),
                ),
                (
                    "source_uuid",
                    models.ForeignKey(
                        db_column="source_uuid",
                        null=True,
                        on_delete=models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
            options={
                "db_table": "reporting_ocp_gpu_summary_by_project_p",
            },
        ),
        # Create OCPGpuSummaryByNodeP table
        migrations.CreateModel(
            name="OCPGpuSummaryByNodeP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("gpu_vendor_name", models.CharField(max_length=128, null=True)),
                ("gpu_model_name", models.CharField(max_length=128, null=True)),
                ("gpu_memory_capacity_mib", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("gpu_hours", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("gpu_count", models.IntegerField(null=True)),
                ("gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("unallocated_gpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("raw_currency", models.TextField(null=True)),
                ("cost_model_cpu_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_memory_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_volume_cost", models.DecimalField(decimal_places=15, max_digits=33, null=True)),
                ("cost_model_rate_type", models.TextField(null=True)),
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True, on_delete=models.deletion.CASCADE, to="reporting.openshiftcostcategory"
                    ),
                ),
                (
                    "source_uuid",
                    models.ForeignKey(
                        db_column="source_uuid",
                        null=True,
                        on_delete=models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
            options={
                "db_table": "reporting_ocp_gpu_summary_by_node_p",
            },
        ),
        # Add indexes for OCPGpuSummaryP
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgpusumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["cluster_id"], name="ocpgpusumm_cluster_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["namespace"], name="ocpgpusumm_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["node"], name="ocpgpusumm_node_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["gpu_vendor_name"], name="ocpgpusumm_vendor_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummaryp",
            index=models.Index(fields=["gpu_model_name"], name="ocpgpusumm_model_idx"),
        ),
        # Add indexes for OCPGpuSummaryByProjectP
        migrations.AddIndex(
            model_name="ocpgpusummarybyprojectp",
            index=models.Index(fields=["usage_start"], name="ocpgpuproj_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybyprojectp",
            index=models.Index(fields=["cluster_id"], name="ocpgpuproj_cluster_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybyprojectp",
            index=models.Index(fields=["namespace"], name="ocpgpuproj_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybyprojectp",
            index=models.Index(fields=["gpu_vendor_name"], name="ocpgpuproj_vendor_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybyprojectp",
            index=models.Index(fields=["gpu_model_name"], name="ocpgpuproj_model_idx"),
        ),
        # Add indexes for OCPGpuSummaryByNodeP
        migrations.AddIndex(
            model_name="ocpgpusummarybynodep",
            index=models.Index(fields=["usage_start"], name="ocpgpunode_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybynodep",
            index=models.Index(fields=["cluster_id"], name="ocpgpunode_cluster_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybynodep",
            index=models.Index(fields=["node"], name="ocpgpunode_node_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybynodep",
            index=models.Index(fields=["gpu_vendor_name"], name="ocpgpunode_vendor_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgpusummarybynodep",
            index=models.Index(fields=["gpu_model_name"], name="ocpgpunode_model_idx"),
        ),
        # Add gpu_uptime_hours field to OCPUsageLineItemDailySummary
        migrations.AddField(
            model_name="ocpusagelineitemdailysummary",
            name="gpu_uptime_hours",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
    ]
