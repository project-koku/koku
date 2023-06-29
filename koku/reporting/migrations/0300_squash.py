import logging
import os
import uuid
from decimal import Decimal

import django.contrib.postgres.fields
import django.contrib.postgres.indexes
import django.db.models.deletion
from django.db import migrations
from django.db import models

import reporting.partition.models
from koku import migration_sql_helpers as msh
from koku.database import set_pg_extended_mode
from koku.database import unset_pg_extended_mode


LOG = logging.getLogger(__name__)
SQL_TMPL = "alter table {} alter column id set default uuid_generate_v4();"
TABLES_P = [
    "reporting_aws_compute_summary_p",
    "reporting_aws_compute_summary_by_account_p",
    "reporting_aws_cost_summary_p",
    "reporting_aws_cost_summary_by_account_p",
    "reporting_aws_cost_summary_by_region_p",
    "reporting_aws_cost_summary_by_service_p",
    "reporting_aws_storage_summary_p",
    "reporting_aws_storage_summary_by_account_p",
    "reporting_aws_database_summary_p",
    "reporting_aws_network_summary_p",
    "reporting_ocpaws_compute_summary_p",
    "reporting_ocpaws_cost_summary_p",
    "reporting_ocpaws_cost_summary_by_account_p",
    "reporting_ocpaws_cost_summary_by_region_p",
    "reporting_ocpaws_cost_summary_by_service_p",
    "reporting_ocpaws_database_summary_p",
    "reporting_ocpaws_network_summary_p",
    "reporting_ocpaws_storage_summary_p",
    "reporting_azure_compute_summary_p",
    "reporting_azure_cost_summary_p",
    "reporting_azure_cost_summary_by_account_p",
    "reporting_azure_cost_summary_by_location_p",
    "reporting_azure_cost_summary_by_service_p",
    "reporting_azure_database_summary_p",
    "reporting_azure_network_summary_p",
    "reporting_azure_storage_summary_p",
    "reporting_ocpazure_compute_summary_p",
    "reporting_ocpazure_cost_summary_p",
    "reporting_ocpazure_cost_summary_by_account_p",
    "reporting_ocpazure_cost_summary_by_location_p",
    "reporting_ocpazure_cost_summary_by_service_p",
    "reporting_ocpazure_database_summary_p",
    "reporting_ocpazure_network_summary_p",
    "reporting_ocpazure_storage_summary_p",
    "reporting_gcp_cost_summary_p",
    "reporting_gcp_cost_summary_by_account_p",
    "reporting_gcp_cost_summary_by_project_p",
    "reporting_gcp_cost_summary_by_region_p",
    "reporting_gcp_cost_summary_by_service_p",
    "reporting_gcp_compute_summary_p",
    "reporting_gcp_compute_summary_by_account_p",
    "reporting_gcp_storage_summary_p",
    "reporting_gcp_storage_summary_by_project_p",
    "reporting_gcp_storage_summary_by_service_p",
    "reporting_gcp_storage_summary_by_account_p",
    "reporting_gcp_storage_summary_by_region_p",
    "reporting_gcp_network_summary_p",
    "reporting_gcp_database_summary_p",
    "reporting_ocpgcp_cost_summary_p",
    "reporting_ocpgcp_compute_summary_p",
    "reporting_ocpgcp_cost_summary_by_account_p",
    "reporting_ocpgcp_cost_summary_by_gcp_project_p",
    "reporting_ocpgcp_cost_summary_by_region_p",
    "reporting_ocpgcp_cost_summary_by_service_p",
    "reporting_ocpgcp_database_summary_p",
    "reporting_ocpgcp_network_summary_p",
    "reporting_ocpgcp_storage_summary_p",
    "reporting_ocp_cost_summary_p",
    "reporting_ocp_cost_summary_by_node_p",
    "reporting_ocp_cost_summary_by_project_p",
    "reporting_ocp_pod_summary_p",
    "reporting_ocp_pod_summary_by_project_p",
    "reporting_ocp_volume_summary_p",
    "reporting_ocp_volume_summary_by_project_p",
    "reporting_ocpallcostlineitem_project_daily_summary_p",
    "reporting_ocpallcostlineitem_daily_summary_p",
    "reporting_ocpall_compute_summary_pt",
    "reporting_ocpall_cost_summary_by_account_pt",
    "reporting_ocpall_cost_summary_by_region_pt",
    "reporting_ocpall_cost_summary_by_service_pt",
    "reporting_ocpall_cost_summary_pt",
    "reporting_ocpall_database_summary_pt",
    "reporting_ocpall_network_summary_pt",
    "reporting_ocpall_storage_summary_pt",
    "reporting_oci_compute_summary_by_account_p",
    "reporting_oci_compute_summary_p",
    "reporting_oci_cost_summary_by_account_p",
    "reporting_oci_cost_summary_by_region_p",
    "reporting_oci_cost_summary_by_service_p",
    "reporting_oci_cost_summary_p",
    "reporting_oci_database_summary_p",
    "reporting_oci_network_summary_p",
    "reporting_oci_storage_summary_by_account_p",
    "reporting_oci_storage_summary_p",
]


def alter_ids(apps, schema_editor):
    LOG.info("ALTERING IDS")
    with schema_editor.connection.cursor() as cur:
        for table in TABLES_P:
            sql = SQL_TMPL.format(table)
            cur.execute(sql)
    LOG.info("CREATING INDICES")


def apply_partitioned_tables_trigger(apps, schema_editor):
    path = msh.find_db_functions_dir()
    for funcfile in ("partitioned_manage_trigger.sql",):
        msh.apply_sql_file(schema_editor, os.path.join(path, funcfile))


class Migration(migrations.Migration):
    replaces = [
        ("reporting", "0250_squash"),
        ("reporting", "0251_update_storageclass_charfields"),
        ("reporting", "0252_alter_ocpusagelineitemdailysummary_monthly_cost_type"),
        ("reporting", "0253_ocpusagereportperiod_ocp_on_cloud_updated_datetime"),
        ("reporting", "0254_oci_models"),
        ("reporting", "0255_ocp_label_indices"),
        ("reporting", "0256_enabled_keys_migration"),
        ("reporting", "0257_raw_currency_ocp_on_cloud"),
        ("reporting", "0258_aws_azure_daily_summ_idxs"),
        ("reporting", "0259_ocpnode_node_role"),
        ("reporting", "0260_productcode_textfields"),
        ("reporting", "0261_ocpgcpcostlineitemprojectdailysummaryp_pod_credit"),
        ("reporting", "0262_standard_numeric_on_calculated_feilds"),
        ("reporting", "0263_add_cost_categroy"),
        ("reporting", "0264_ocpaws_cost_fields"),
        ("reporting", "0265_auto_20221114_1806"),
        ("reporting", "0266_ocpgcp_precision"),
        ("reporting", "0267_update_cost_category"),
        ("reporting", "0268_ingressreports"),
        ("reporting", "0269_auto_20230127_1627"),
        ("reporting", "0270_ocp_distribution_cost"),
        ("reporting", "0271_alter_ocpenabledtagkeys_enabled"),
        ("reporting", "0272_auto_20230309_1924"),
        ("reporting", "0273_ocp_on_cloud_namespace"),
        ("reporting", "0274_alter_ocpallcostlineitemprojectdailysummaryp_namespace"),
        ("reporting", "0275_aws_category_tables"),
        ("reporting", "0276_auto_20230303_1947"),
        ("reporting", "0277_store_aws_amoritized_cost"),
        ("reporting", "0278_ocpcluster_remove_duplicates"),
        ("reporting", "0279_ocp_alter_unique_together"),
        ("reporting", "0280_markup_amortized_cost"),
        ("reporting", "0281_tenantapiprovider"),
        ("reporting", "0282_auto_20230608_1819"),
        ("reporting", "0283_auto_20230612_1841"),
        ("reporting", "0284_auto_20230613_1624"),
        ("reporting", "0285_auto_20230614_1338"),
        ("reporting", "0286_auto_20230614_2202"),
        ("reporting", "0287_auto_20230615_1523"),
        ("reporting", "0288_auto_20230615_1658"),
        ("reporting", "0289_alter_awsorganizationalunit_provider"),
        ("reporting", "0290_update_settings"),
        ("reporting", "0291_awsenabledcategorykeys_uuid"),
        ("reporting", "0292_auto_20230628_2317"),
    ]

    initial = True

    dependencies = [
        ("api", "0056_reapply_clone_schema_func"),
        ("api", "0050_exchangerates"),
        ("api", "0059_alter_tenant_schema"),
        ("api", "0049_auto_20210818_2208"),
        ("api", "0058_exchangeratedictionary"),
        ("api", "0001_initial"),
    ]
    operations = [
        migrations.RunSQL(sql="\ncreate extension if not exists pg_trgm schema public;\n"),
        migrations.RunPython(code=set_pg_extended_mode, reverse_code=unset_pg_extended_mode),
        migrations.CreateModel(
            name="TenantAPIProvider",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("name", models.TextField()),
                ("type", models.TextField()),
                (
                    "provider",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="api.provider",
                    ),
                ),
            ],
            options={
                "db_table": "reporting_tenant_api_provider",
            },
        ),
        migrations.CreateModel(
            name="OpenshiftCostCategory",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.TextField(unique=True)),
                ("description", models.TextField()),
                ("source_type", models.TextField()),
                ("system_default", models.BooleanField(default=False)),
                (
                    "namespace",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "label",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
            ],
            options={
                "db_table": "reporting_ocp_cost_category",
            },
        ),
        migrations.CreateModel(
            name="IngressReports",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("uuid", models.UUIDField(default=uuid.uuid4)),
                ("created_timestamp", models.DateTimeField(auto_now_add=True)),
                ("completed_timestamp", models.DateTimeField(null=True)),
                (
                    "reports_list",
                    django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=256), size=None),
                ),
                ("bill_year", models.CharField(max_length=4)),
                ("bill_month", models.CharField(max_length=2)),
                (
                    "source",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="api.provider"),
                ),
                ("sources_id", models.IntegerField(null=True)),
                ("status", models.TextField(default="pending")),
            ],
        ),
        migrations.CreateModel(
            name="OCPAllCostLineItemDailySummary",
            fields=[
                ("id", models.IntegerField(primary_key=True, serialize=False)),
                ("source_type", models.TextField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "namespace",
                    django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=253), size=None),
                ),
                ("node", models.CharField(max_length=253, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                ("tags", models.JSONField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("shared_projects", models.IntegerField(default=1)),
                ("source_uuid", models.UUIDField(null=True)),
                ("tags_hash", models.TextField(max_length=512)),
            ],
            options={
                "db_table": "reporting_ocpallcostlineitem_daily_summary",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="OCPAllCostLineItemProjectDailySummary",
            fields=[
                ("id", models.IntegerField(primary_key=True, serialize=False)),
                ("source_type", models.TextField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("namespace", models.CharField(max_length=253)),
                ("node", models.CharField(max_length=253, null=True)),
                ("pod_labels", models.JSONField(null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "project_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "pod_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_uuid", models.UUIDField(null=True)),
            ],
            options={
                "db_table": "reporting_ocpallcostlineitem_project_daily_summary",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="AWSAccountAlias",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("account_id", models.CharField(max_length=50, unique=True)),
                ("account_alias", models.CharField(max_length=63, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="AWSOrganizationalUnit",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("org_unit_name", models.CharField(max_length=250)),
                ("org_unit_id", models.CharField(max_length=50)),
                ("org_unit_path", models.TextField()),
                ("level", models.PositiveSmallIntegerField()),
                ("created_timestamp", models.DateField(auto_now_add=True)),
                ("deleted_timestamp", models.DateField(null=True)),
                (
                    "provider",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="reporting.awsaccountalias",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AWSComputeSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_compute_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="AWSComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_aws_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="AWSCostEntryBill",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("billing_resource", models.CharField(default="aws", max_length=50)),
                ("bill_type", models.CharField(max_length=50, null=True)),
                ("payer_account_id", models.CharField(max_length=50, null=True)),
                ("billing_period_start", models.DateTimeField()),
                ("billing_period_end", models.DateTimeField()),
                ("summary_data_creation_datetime", models.DateTimeField(null=True)),
                ("summary_data_updated_datetime", models.DateTimeField(null=True)),
                ("finalized_datetime", models.DateTimeField(null=True)),
                ("derived_cost_datetime", models.DateTimeField(null=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AWSCostEntryLineItemDailySummary",
            fields=[
                ("uuid", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField(null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
                ("resource_count", models.IntegerField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("normalization_factor", models.FloatField(null=True)),
                ("normalized_usage_amount", models.FloatField(null=True)),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "unblended_rate",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("cost_category", models.JSONField(null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_rate",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "public_on_demand_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "public_on_demand_rate",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("tax_type", models.TextField(null=True)),
                ("tags", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.awscostentrybill",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
                    ),
                ),
            ],
            options={"db_table": "reporting_awscostentrylineitem_daily_summary"},
        ),
        migrations.CreateModel(
            name="AWSCostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="AWSCostSummaryByRegionP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_cost_summary_by_region_p"},
        ),
        migrations.CreateModel(
            name="AWSCostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="AWSCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_aws_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="AWSDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_database_summary_p"},
        ),
        migrations.CreateModel(
            name="AWSEnabledTagKeys",
            fields=[
                (
                    "key",
                    models.CharField(max_length=253, primary_key=True, serialize=False),
                ),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"db_table": "reporting_awsenabledtagkeys"},
        ),
        migrations.RunSQL("""ALTER TABLE reporting_awsenabledtagkeys ALTER COLUMN enabled SET DEFAULT true"""),
        migrations.CreateModel(
            name="AWSNetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_network_summary_p"},
        ),
        migrations.CreateModel(
            name="AWSStorageSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "organizational_unit",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsorganizationalunit",
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
            options={"db_table": "reporting_aws_storage_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="AWSStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_aws_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="AWSTagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("usage_account_id", models.TextField(null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.awscostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_awstags_summary"},
        ),
        migrations.CreateModel(
            name="AWSTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "usage_account_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "account_aliases",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
            ],
            options={"db_table": "reporting_awstags_values"},
        ),
        migrations.CreateModel(
            name="AWSCategorySummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("usage_account_id", models.TextField(null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.awscostentrybill",
                    ),
                ),
            ],
            options={
                "db_table": "reporting_awscategory_summary",
            },
        ),
        migrations.CreateModel(
            name="AWSEnabledCategoryKeys",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("key", models.CharField(max_length=253, unique=True)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "reporting_awsenabledcategorykeys",
            },
        ),
        migrations.CreateModel(
            name="AzureComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("instance_type", models.TextField(null=True)),
                (
                    "instance_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
                ("instance_count", models.IntegerField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="AzureCostEntryBill",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("billing_period_start", models.DateTimeField()),
                ("billing_period_end", models.DateTimeField()),
                ("summary_data_creation_datetime", models.DateTimeField(null=True)),
                ("summary_data_updated_datetime", models.DateTimeField(null=True)),
                ("finalized_datetime", models.DateTimeField(null=True)),
                ("derived_cost_datetime", models.DateTimeField(null=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AzureCostEntryLineItemDailySummary",
            fields=[
                ("uuid", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("subscription_guid", models.TextField()),
                ("instance_type", models.TextField(null=True)),
                ("service_name", models.TextField(null=True)),
                ("resource_location", models.TextField(null=True)),
                ("tags", models.JSONField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "instance_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
                ("instance_count", models.IntegerField(null=True)),
                ("unit_of_measure", models.TextField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.azurecostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_azurecostentrylineitem_daily_summary"},
        ),
        migrations.CreateModel(
            name="AzureCostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="AzureCostSummaryByLocationP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("resource_location", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_cost_summary_by_location_p"},
        ),
        migrations.CreateModel(
            name="AzureCostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField()),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="AzureCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="AzureDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField()),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_database_summary_p"},
        ),
        migrations.CreateModel(
            name="AzureEnabledTagKeys",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=253, unique=True)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"db_table": "reporting_azureenabledtagkeys"},
        ),
        migrations.CreateModel(
            name="AzureNetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField()),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_network_summary_p"},
        ),
        migrations.CreateModel(
            name="AzureStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("subscription_name", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField()),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_azure_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="AzureTagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("subscription_guid", models.TextField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.azurecostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_azuretags_summary"},
        ),
        migrations.CreateModel(
            name="AzureTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "subscription_guids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
            ],
            options={"db_table": "reporting_azuretags_values"},
        ),
        migrations.CreateModel(
            name="OCPUsageReportPeriod",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cluster_id", models.CharField(max_length=50)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("report_period_start", models.DateTimeField()),
                ("report_period_end", models.DateTimeField()),
                ("ocp_on_cloud_updated_datetime", models.DateTimeField(null=True)),
                ("summary_data_creation_datetime", models.DateTimeField(null=True)),
                ("summary_data_updated_datetime", models.DateTimeField(null=True)),
                ("derived_cost_datetime", models.DateTimeField(null=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="CostSummary",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("pod", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "pod_charge_cpu_core_hours",
                    models.DecimalField(decimal_places=9, max_digits=27, null=True),
                ),
                (
                    "pod_charge_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=9, max_digits=27, null=True),
                ),
                (
                    "persistentvolumeclaim_charge_gb_month",
                    models.DecimalField(decimal_places=9, max_digits=27, null=True),
                ),
                (
                    "infra_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "project_infra_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=27, null=True),
                ),
                (
                    "project_markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=27, null=True),
                ),
                ("pod_labels", models.JSONField(null=True)),
                (
                    "monthly_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpcosts_summary"},
        ),
        migrations.CreateModel(
            name="CurrencySettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("currency", models.TextField()),
            ],
            options={"db_table": "currency_settings"},
        ),
        migrations.CreateModel(
            name="GCPComputeSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("account_id", models.CharField(max_length=50)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_compute_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="GCPComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="GCPCostEntryBill",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("billing_period_start", models.DateTimeField()),
                ("billing_period_end", models.DateTimeField()),
                (
                    "summary_data_creation_datetime",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "summary_data_updated_datetime",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("finalized_datetime", models.DateTimeField(blank=True, null=True)),
                ("derived_cost_datetime", models.DateTimeField(blank=True, null=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="GCPCostEntryLineItemDailySummary",
            fields=[
                ("uuid", models.UUIDField(primary_key=True, serialize=False)),
                ("account_id", models.CharField(max_length=20)),
                ("project_id", models.CharField(max_length=256)),
                ("project_name", models.CharField(max_length=256)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                ("sku_id", models.CharField(max_length=256, null=True)),
                ("sku_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField(null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("unit", models.CharField(max_length=63, null=True)),
                ("line_item_type", models.CharField(max_length=256, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("tags", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.gcpcostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_gcpcostentrylineitem_daily_summary"},
        ),
        migrations.CreateModel(
            name="GCPCostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=50)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="GCPCostSummaryByProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("project_id", models.CharField(max_length=256)),
                ("project_name", models.CharField(max_length=256)),
                ("account_id", models.CharField(max_length=50)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_cost_summary_by_project_p"},
        ),
        migrations.CreateModel(
            name="GCPCostSummaryByRegionP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=50)),
                ("region", models.CharField(max_length=50, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_cost_summary_by_region_p"},
        ),
        migrations.CreateModel(
            name="GCPCostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=50)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="GCPCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="GCPDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_database_summary_p"},
        ),
        migrations.CreateModel(
            name="GCPEnabledTagKeys",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=253, unique=True)),
                ("enabled", models.BooleanField(default=False)),
            ],
            options={"db_table": "reporting_gcpenabledtagkeys"},
        ),
        migrations.CreateModel(
            name="GCPNetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_network_summary_p"},
        ),
        migrations.CreateModel(
            name="GCPStorageSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("account_id", models.CharField(max_length=50)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_storage_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="GCPStorageSummaryByProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("project_id", models.CharField(max_length=256)),
                ("project_name", models.CharField(max_length=256)),
                ("account_id", models.CharField(max_length=50)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_storage_summary_by_project_p"},
        ),
        migrations.CreateModel(
            name="GCPStorageSummaryByRegionP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("account_id", models.CharField(max_length=50)),
                ("region", models.CharField(max_length=50, null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_storage_summary_by_region_p"},
        ),
        migrations.CreateModel(
            name="GCPStorageSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                ("account_id", models.CharField(max_length=50)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_storage_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="GCPStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
            options={"db_table": "reporting_gcp_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="GCPTagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("account_id", models.TextField(null=True)),
                ("project_id", models.TextField(null=True)),
                ("project_name", models.TextField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.gcpcostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_gcptags_summary"},
        ),
        migrations.CreateModel(
            name="GCPTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "account_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "project_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
                (
                    "project_names",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
            ],
            options={"db_table": "reporting_gcptags_values"},
        ),
        migrations.CreateModel(
            name="GCPTopology",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("source_uuid", models.UUIDField(null=True)),
                ("account_id", models.TextField()),
                ("project_id", models.TextField()),
                ("project_name", models.TextField()),
                ("service_id", models.TextField()),
                ("service_alias", models.TextField()),
                ("region", models.TextField()),
            ],
            options={"db_table": "reporting_gcp_topology"},
        ),
        migrations.CreateModel(
            name="OCPAllComputeSummaryPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_code", models.CharField(max_length=50)),
                ("instance_type", models.CharField(max_length=50)),
                ("resource_id", models.CharField(max_length=253)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_compute_summary_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllCostLineItemDailySummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("source_type", models.TextField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "namespace",
                    django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=253), size=None),
                ),
                ("node", models.CharField(max_length=253, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                ("tags", models.JSONField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("shared_projects", models.IntegerField(default=1)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpallcostlineitem_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAllCostLineItemProjectDailySummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("source_type", models.TextField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("pod_labels", models.JSONField(null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "project_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "pod_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpallcostlineitem_project_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAllCostSummaryByAccountPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_cost_summary_by_account_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllCostSummaryByRegionPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_cost_summary_by_region_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllCostSummaryByServicePT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_cost_summary_by_service_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllCostSummaryPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
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
            options={"db_table": "reporting_ocpall_cost_summary_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllDatabaseSummaryPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_code", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_database_summary_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllNetworkSummaryPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_code", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_network_summary_pt"},
        ),
        migrations.CreateModel(
            name="OCPAllStorageSummaryPT",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("product_code", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency_code", models.CharField(max_length=10, null=True)),
                ("source_type", models.TextField(default="")),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpall_storage_summary_pt"},
        ),
        migrations.CreateModel(
            name="OCPAWSComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSCostLineItemDailySummaryP",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "namespace",
                    django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=253), size=None),
                ),
                ("node", models.CharField(max_length=253, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_code", models.TextField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("unit", models.CharField(max_length=63, null=True)),
                ("tags", models.JSONField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("normalized_usage_amount", models.FloatField(null=True)),
                ("currency_code", models.CharField(max_length=10, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("shared_projects", models.IntegerField(default=1)),
                ("project_costs", models.JSONField(null=True)),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.awscostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
            options={"db_table": "reporting_ocpawscostlineitem_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSCostLineItemProjectDailySummaryP",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("persistentvolumeclaim", models.CharField(max_length=253, null=True)),
                ("persistentvolume", models.CharField(max_length=253, null=True)),
                ("storageclass", models.CharField(max_length=50, null=True)),
                ("pod_labels", models.JSONField(null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("product_code", models.TextField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                ("region", models.CharField(max_length=50, null=True)),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("normalized_usage_amount", models.FloatField(null=True)),
                ("currency_code", models.CharField(max_length=10, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "project_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "pod_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("tags", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.awscostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
                ("aws_cost_category", models.JSONField(null=True)),
            ],
            options={"db_table": "reporting_ocpawscostlineitem_project_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSCostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSCostSummaryByRegionP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("region", models.CharField(max_length=50, null=True)),
                ("availability_zone", models.CharField(max_length=50, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_cost_summary_by_region_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSCostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                ("product_family", models.CharField(max_length=150, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_ocpaws_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_database_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSNetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_code", models.TextField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_network_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_account_id", models.CharField(max_length=50)),
                ("product_family", models.CharField(max_length=150, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "blended_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_blended",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_savingsplan",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost_amortized",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                (
                    "savingsplan_effective_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "calculated_amortized_cost",
                    models.DecimalField(decimal_places=9, max_digits=33, null=True),
                ),
                ("currency_code", models.CharField(max_length=10)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        to="reporting.awsaccountalias",
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpaws_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAWSTagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.CharField(max_length=253)),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("usage_account_id", models.CharField(max_length=50, null=True)),
                ("namespace", models.TextField()),
                ("node", models.TextField(null=True)),
                (
                    "account_alias",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="reporting.awsaccountalias",
                    ),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.awscostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpawstags_summary"},
        ),
        migrations.CreateModel(
            name="OCPAWSTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "usage_account_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "account_aliases",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_aliases",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "namespaces",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "nodes",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
            ],
            options={"db_table": "reporting_ocpawstags_values"},
        ),
        migrations.CreateModel(
            name="OCPAzureComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                ("instance_type", models.TextField(null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureCostLineItemDailySummaryP",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "namespace",
                    django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=253), size=None),
                ),
                ("node", models.CharField(max_length=253, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("instance_type", models.TextField(null=True)),
                ("service_name", models.TextField(null=True)),
                ("resource_location", models.TextField(null=True)),
                ("tags", models.JSONField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=17, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=17, null=True),
                ),
                ("currency", models.TextField(null=True)),
                ("unit_of_measure", models.TextField(null=True)),
                ("shared_projects", models.IntegerField(default=1)),
                ("project_costs", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.azurecostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
            options={"db_table": "reporting_ocpazurecostlineitem_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureCostLineItemProjectDailySummaryP",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("persistentvolumeclaim", models.CharField(max_length=253, null=True)),
                ("persistentvolume", models.CharField(max_length=253, null=True)),
                ("storageclass", models.CharField(max_length=50, null=True)),
                ("pod_labels", models.JSONField(null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("subscription_guid", models.TextField()),
                ("instance_type", models.TextField(null=True)),
                ("service_name", models.TextField(null=True)),
                ("resource_location", models.TextField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                ("currency", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=9, max_digits=17, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=17, null=True),
                ),
                (
                    "project_markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=17, null=True),
                ),
                (
                    "pod_cost",
                    models.DecimalField(decimal_places=6, max_digits=24, null=True),
                ),
                ("tags", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.azurecostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
            options={"db_table": "reporting_ocpazurecostlineitem_project_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureCostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureCostSummaryByLocationP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                ("resource_location", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_cost_summary_by_location_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureCostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_database_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureNetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_network_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("subscription_guid", models.TextField()),
                ("service_name", models.TextField(null=True)),
                (
                    "usage_quantity",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("unit_of_measure", models.TextField(null=True)),
                (
                    "pretax_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("currency", models.TextField(null=True)),
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
            options={"db_table": "reporting_ocpazure_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPAzureTagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.CharField(max_length=253)),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("subscription_guid", models.TextField(null=True)),
                ("namespace", models.TextField()),
                ("node", models.TextField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.azurecostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpazuretags_summary"},
        ),
        migrations.CreateModel(
            name="OCPAzureTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "subscription_guids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_aliases",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "namespaces",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "nodes",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
            ],
            options={"db_table": "reporting_ocpazuretags_values"},
        ),
        migrations.CreateModel(
            name="OCPCluster",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.tenantapiprovider",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocp_clusters"},
        ),
        migrations.CreateModel(
            name="OCPCostSummaryByNodeP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_cost_summary_by_node_p"},
        ),
        migrations.CreateModel(
            name="OCPCostSummaryByProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_project_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "infrastructure_project_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_project_monthly_cost", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_project_monthly_cost", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_cost_summary_by_project_p"},
        ),
        migrations.CreateModel(
            name="OCPCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPEnabledTagKeys",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=253, unique=True)),
                ("enabled", models.BooleanField(default=False)),
            ],
            options={"db_table": "reporting_ocpenabledtagkeys"},
        ),
        migrations.CreateModel(
            name="OCPGCPComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
                ),
                ("account_id", models.CharField(max_length=50)),
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
            options={"db_table": "reporting_ocpgcp_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostLineItemDailySummaryP",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                (
                    "namespace",
                    django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=253), size=None),
                ),
                ("node", models.CharField(max_length=253, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=20)),
                ("project_id", models.CharField(max_length=256)),
                ("project_name", models.CharField(max_length=256)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                ("region", models.TextField(null=True)),
                ("tags", models.JSONField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=17, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                ("unit", models.TextField(null=True)),
                ("shared_projects", models.IntegerField(default=1)),
                ("project_costs", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.gcpcostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
            options={"db_table": "reporting_ocpgcpcostlineitem_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostLineItemProjectDailySummaryP",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("persistentvolumeclaim", models.CharField(max_length=253, null=True)),
                ("persistentvolume", models.CharField(max_length=253, null=True)),
                ("storageclass", models.CharField(max_length=50, null=True)),
                ("pod_labels", models.JSONField(null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=20)),
                ("project_id", models.CharField(max_length=256)),
                ("project_name", models.CharField(max_length=256)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                ("sku_id", models.CharField(max_length=256, null=True)),
                ("sku_alias", models.CharField(max_length=256, null=True)),
                ("region", models.TextField(null=True)),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.CharField(max_length=10, null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "project_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "pod_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("tags", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "pod_credit",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.gcpcostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
            options={"db_table": "reporting_ocpgcpcostlineitem_project_daily_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=20)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostSummaryByGCPProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("project_id", models.CharField(max_length=256)),
                ("project_name", models.CharField(max_length=256)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_cost_summary_by_gcp_project_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostSummaryByRegionP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("account_id", models.CharField(max_length=50)),
                ("region", models.TextField(null=True)),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_cost_summary_by_region_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                ("account_id", models.CharField(max_length=50)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPCostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                ("account_id", models.CharField(max_length=50)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_database_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPNetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                ("account_id", models.CharField(max_length=50)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_network_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                ("account_id", models.CharField(max_length=50)),
                ("service_id", models.CharField(max_length=256, null=True)),
                (
                    "service_alias",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "unblended_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=30, null=True),
                ),
                ("currency", models.TextField(null=True)),
                (
                    "invoice_month",
                    models.CharField(blank=True, max_length=256, null=True),
                ),
                (
                    "credit_amount",
                    models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True),
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
                (
                    "cost_category",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.openshiftcostcategory",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcp_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPGCPTagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.CharField(max_length=253)),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("account_id", models.TextField()),
                ("project_id", models.TextField()),
                ("project_name", models.TextField()),
                ("namespace", models.TextField()),
                ("node", models.TextField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.gcpcostentrybill",
                    ),
                ),
                (
                    "report_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpgcptags_summary"},
        ),
        migrations.CreateModel(
            name="OCPGCPTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "account_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "project_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "project_names",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_aliases",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "namespaces",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "nodes",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
            ],
            options={"db_table": "reporting_ocpgcptags_values"},
        ),
        migrations.CreateModel(
            name="OCPNode",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("node", models.TextField()),
                ("resource_id", models.TextField(null=True)),
                (
                    "node_capacity_cpu_cores",
                    models.DecimalField(decimal_places=2, max_digits=18, null=True),
                ),
                ("node_role", models.TextField(null=True)),
                (
                    "cluster",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpcluster",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocp_nodes"},
        ),
        migrations.CreateModel(
            name="OCPPodSummaryByProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_usage_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_request_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_effective_usage_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_limit_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_usage_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_request_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_effective_usage_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_limit_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cluster_capacity_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cluster_capacity_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_pod_summary_by_project_p"},
        ),
        migrations.CreateModel(
            name="OCPPodSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_usage_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_request_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_effective_usage_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_limit_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_usage_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_request_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_effective_usage_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_limit_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cluster_capacity_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cluster_capacity_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_pod_summary_p"},
        ),
        migrations.CreateModel(
            name="OCPProject",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("project", models.TextField()),
                (
                    "cluster",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpcluster",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocp_projects"},
        ),
        migrations.CreateModel(
            name="OCPPVC",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("persistent_volume_claim", models.TextField()),
                ("persistent_volume", models.TextField()),
                (
                    "cluster",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpcluster",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocp_pvcs"},
        ),
        migrations.CreateModel(
            name="OCPStorageVolumeLabelSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("namespace", models.TextField()),
                ("node", models.TextField(null=True)),
                (
                    "report_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpstoragevolumelabel_summary"},
        ),
        migrations.CreateModel(
            name="OCPTagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "cluster_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "cluster_aliases",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "namespaces",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                (
                    "nodes",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
            ],
            options={"db_table": "reporting_ocptags_values"},
        ),
        migrations.CreateModel(
            name="OCPUsageLineItemDailySummary",
            fields=[
                ("uuid", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.CharField(max_length=50, null=True)),
                ("cluster_alias", models.CharField(max_length=256, null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                ("node", models.CharField(max_length=253, null=True)),
                ("resource_id", models.CharField(max_length=253, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("pod_labels", models.JSONField(null=True)),
                (
                    "pod_usage_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_request_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_effective_usage_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_limit_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_usage_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_request_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_effective_usage_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "pod_limit_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "node_capacity_cpu_cores",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "node_capacity_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "node_capacity_memory_gigabytes",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "node_capacity_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cluster_capacity_cpu_core_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cluster_capacity_memory_gigabyte_hours",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("persistentvolumeclaim", models.CharField(max_length=253, null=True)),
                ("persistentvolume", models.CharField(max_length=253, null=True)),
                ("storageclass", models.CharField(max_length=50, null=True)),
                ("volume_labels", models.JSONField(null=True)),
                (
                    "persistentvolumeclaim_capacity_gigabyte",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "persistentvolumeclaim_capacity_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "volume_request_storage_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "persistentvolumeclaim_usage_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(
                        decimal_places=15,
                        default=Decimal("0"),
                        max_digits=33,
                        null=True,
                    ),
                ),
                (
                    "infrastructure_project_raw_cost",
                    models.DecimalField(
                        decimal_places=15,
                        default=Decimal("0"),
                        max_digits=33,
                        null=True,
                    ),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "infrastructure_project_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "infrastructure_monthly_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                (
                    "supplementary_monthly_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                ("infrastructure_project_monthly_cost", models.JSONField(null=True)),
                ("supplementary_project_monthly_cost", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "monthly_cost_type",
                    models.TextField(
                        choices=[
                            ("Node", "Node"),
                            ("Cluster", "Cluster"),
                            ("PVC", "PVC"),
                            ("Tag", "Tag"),
                        ],
                        null=True,
                    ),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("raw_currency", models.TextField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "report_period",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
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
            options={"db_table": "reporting_ocpusagelineitem_daily_summary"},
        ),
        migrations.CreateModel(
            name="OCPUsagePodLabelSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("namespace", models.TextField()),
                ("node", models.TextField(null=True)),
                (
                    "report_period",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocpusagereportperiod",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocpusagepodlabel_summary"},
        ),
        migrations.CreateModel(
            name="OCPVolumeSummaryByProjectP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                ("namespace", models.CharField(max_length=253, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "volume_request_storage_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "persistentvolumeclaim_usage_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "persistentvolumeclaim_capacity_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_volume_summary_by_project_p"},
        ),
        migrations.CreateModel(
            name="OCPVolumeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("cluster_id", models.TextField()),
                ("cluster_alias", models.TextField(null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                ("data_source", models.CharField(max_length=64, null=True)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "infrastructure_raw_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_usage_cost", models.JSONField(null=True)),
                (
                    "infrastructure_markup_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                ("infrastructure_monthly_cost_json", models.JSONField(null=True)),
                ("supplementary_usage_cost", models.JSONField(null=True)),
                ("supplementary_monthly_cost_json", models.JSONField(null=True)),
                (
                    "cost_model_cpu_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_memory_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_rate_type",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "cost_model_volume_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "volume_request_storage_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "persistentvolumeclaim_usage_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "persistentvolumeclaim_capacity_gigabyte_months",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                (
                    "distributed_cost",
                    models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
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
            options={"db_table": "reporting_ocp_volume_summary_p"},
        ),
        migrations.CreateModel(
            name="OCICostEntryBill",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("billing_resource", models.CharField(default="oci", max_length=80)),
                ("bill_type", models.CharField(max_length=50, null=True)),
                ("payer_tenant_id", models.CharField(max_length=80, null=True)),
                ("billing_period_start", models.DateTimeField()),
                ("billing_period_end", models.DateTimeField()),
                ("summary_data_creation_datetime", models.DateTimeField(null=True)),
                ("summary_data_updated_datetime", models.DateTimeField(null=True)),
                ("finalized_datetime", models.DateTimeField(null=True)),
                ("derived_cost_datetime", models.DateTimeField(null=True)),
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
        ),
        migrations.CreateModel(
            name="OCIComputeSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_compute_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="OCIComputeSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("instance_type", models.CharField(max_length=50, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.CharField(max_length=256),
                        null=True,
                        size=None,
                    ),
                ),
                ("resource_count", models.IntegerField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_compute_summary_p"},
        ),
        migrations.CreateModel(
            name="OCICostEntryLineItemDailySummary",
            fields=[
                ("uuid", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField(null=True)),
                ("payer_tenant_id", models.CharField(max_length=80)),
                ("product_service", models.CharField(max_length=50)),
                ("region", models.CharField(max_length=50, null=True)),
                ("instance_type", models.CharField(max_length=50, null=True)),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "resource_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), null=True, size=None),
                ),
                ("resource_count", models.IntegerField(null=True)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("tags", models.JSONField(null=True)),
                ("source_uuid", models.UUIDField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocicostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocicostentrylineitem_daily_summary"},
        ),
        migrations.CreateModel(
            name="OCICostSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_cost_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="OCICostSummaryByRegionP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                ("region", models.CharField(max_length=50, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_cost_summary_by_region_p"},
        ),
        migrations.CreateModel(
            name="OCICostSummaryByServiceP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                ("product_service", models.CharField(max_length=50)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_cost_summary_by_service_p"},
        ),
        migrations.CreateModel(
            name="OCICostSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_cost_summary_p"},
        ),
        migrations.CreateModel(
            name="OCIDatabaseSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                ("product_service", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_database_summary_p"},
        ),
        migrations.CreateModel(
            name="OCINetworkSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                ("product_service", models.CharField(max_length=50)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_network_summary_p"},
        ),
        migrations.CreateModel(
            name="OCIStorageSummaryByAccountP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                ("payer_tenant_id", models.CharField(max_length=80)),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("product_service", models.CharField(max_length=50)),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_storage_summary_by_account_p"},
        ),
        migrations.CreateModel(
            name="OCIStorageSummaryP",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False)),
                ("usage_start", models.DateField()),
                ("usage_end", models.DateField()),
                (
                    "usage_amount",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("product_service", models.CharField(max_length=50)),
                ("unit", models.CharField(max_length=63, null=True)),
                (
                    "cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                (
                    "markup_cost",
                    models.DecimalField(decimal_places=9, max_digits=24, null=True),
                ),
                ("currency", models.CharField(max_length=10)),
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
            options={"db_table": "reporting_oci_storage_summary_p"},
        ),
        migrations.CreateModel(
            name="OCIEnabledTagKeys",
            fields=[
                (
                    "key",
                    models.CharField(max_length=253, primary_key=True, serialize=False),
                ),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"db_table": "reporting_ocienabledtagkeys"},
        ),
        migrations.CreateModel(
            name="OCITagsSummary",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                (
                    "values",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
                ("payer_tenant_id", models.TextField(null=True)),
                (
                    "cost_entry_bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="reporting.ocicostentrybill",
                    ),
                ),
            ],
            options={"db_table": "reporting_ocitags_summary"},
        ),
        migrations.CreateModel(
            name="OCITagsValues",
            fields=[
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False),
                ),
                ("key", models.TextField()),
                ("value", models.TextField()),
                (
                    "payer_tenant_ids",
                    django.contrib.postgres.fields.ArrayField(base_field=models.TextField(), size=None),
                ),
            ],
            options={"db_table": "reporting_ocitags_values"},
        ),
        migrations.CreateModel(
            name="PartitionedTable",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "schema_name",
                    models.TextField(validators=[reporting.partition.models.validate_not_empty]),
                ),
                (
                    "table_name",
                    models.TextField(validators=[reporting.partition.models.validate_not_empty]),
                ),
                (
                    "partition_of_table_name",
                    models.TextField(validators=[reporting.partition.models.validate_not_empty]),
                ),
                (
                    "partition_type",
                    models.TextField(validators=[reporting.partition.models.validate_not_empty]),
                ),
                (
                    "partition_col",
                    models.TextField(validators=[reporting.partition.models.validate_not_empty]),
                ),
                (
                    "partition_parameters",
                    models.JSONField(validators=[reporting.partition.models.validate_not_empty]),
                ),
                ("active", models.BooleanField(default=True)),
                ("subpartition_type", models.TextField(null=True)),
                ("subpartition_col", models.TextField(null=True)),
            ],
            options={"db_table": "partitioned_tables"},
        ),
        migrations.CreateModel(
            name="UserSettings",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("settings", models.JSONField()),
            ],
            options={"db_table": "user_settings"},
        ),
        migrations.RunPython(code=alter_ids, reverse_code=migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="partitionedtable",
            index=models.Index(fields=["schema_name", "table_name"], name="partable_table"),
        ),
        migrations.AddIndex(
            model_name="partitionedtable",
            index=models.Index(fields=["partition_type"], name="partable_partition_type"),
        ),
        migrations.AddIndex(
            model_name="partitionedtable",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["partition_parameters"], name="partable_partition_parameters"
            ),
        ),
        migrations.AlterUniqueTogether(name="partitionedtable", unique_together={("schema_name", "table_name")}),
        migrations.RunSQL("""ALTER TABLE partitioned_tables ALTER COLUMN active SET DEFAULT true"""),
        migrations.RunPython(
            code=apply_partitioned_tables_trigger,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddIndex(
            model_name="ocptagsvalues",
            index=models.Index(fields=["key"], name="openshift_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="ocptagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="ocpgcptagsvalues",
            index=models.Index(fields=["key"], name="ocp_gcp_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="ocpgcptagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="ocpazuretagsvalues",
            index=models.Index(fields=["key"], name="ocp_azure_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="ocpazuretagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="ocpawstagsvalues",
            index=models.Index(fields=["key"], name="ocp_aws_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="ocpawstagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="gcptagsvalues",
            index=models.Index(fields=["key"], name="gcp_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="gcptagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="azuretagsvalues",
            index=models.Index(fields=["key"], name="azure_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="azuretagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="awstagsvalues",
            index=models.Index(fields=["key"], name="aws_tags_value_key_idx"),
        ),
        migrations.AlterUniqueTogether(name="awstagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="awsenabledtagkeys",
            index=models.Index(fields=["key", "enabled"], name="aws_enabled_key_index"),
        ),
        migrations.AddIndex(
            model_name="ocitagsvalues",
            index=models.Index(fields=["key"], name="oci_tags_value_key_idx"),
        ),
        migrations.AddIndex(
            model_name="ocienabledtagkeys",
            index=models.Index(fields=["key", "enabled"], name="oci_enabled_key_index"),
        ),
        migrations.AddIndex(
            model_name="azureenabledtagkeys",
            index=models.Index(fields=["key", "enabled"], name="azure_enabled_covering_ix"),
        ),
        migrations.AddIndex(
            model_name="gcpenabledtagkeys",
            index=models.Index(fields=["key", "enabled"], name="gcp_enabled_covering_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpenabledtagkeys",
            index=models.Index(fields=["key", "enabled"], name="ocp_enabled_covering_ix"),
        ),
        migrations.AddIndex(
            model_name="awsenabledcategorykeys",
            index=models.Index(fields=["key", "enabled"], name="aws_enabled_category_key_index"),
        ),
        migrations.AlterUniqueTogether(
            name="awscategorysummary",
            unique_together={("key", "cost_entry_bill", "usage_account_id")},
        ),
        migrations.AlterUniqueTogether(name="ocitagsvalues", unique_together={("key", "value")}),
        migrations.AddIndex(
            model_name="ocpvolumesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpvolsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpvolumesummarybyprojectp",
            index=models.Index(fields=["usage_start"], name="ocpvolsumm_proj_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpvolumesummarybyprojectp",
            index=models.Index(fields=["namespace"], name="ocpvolsumm_proj_namespace"),
        ),
        migrations.AlterUniqueTogether(
            name="ocpusagereportperiod",
            unique_together={("cluster_id", "report_period_start", "provider")},
        ),
        migrations.AlterUniqueTogether(
            name="ocpusagepodlabelsummary",
            unique_together={("key", "report_period", "namespace", "node")},
        ),
        migrations.AddIndex(
            model_name="ocpusagepodlabelsummary",
            index=models.Index(fields=["key"], name="openshift_pod_label_key_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(fields=["usage_start"], name="summary_ocp_usage_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(
                fields=["namespace"],
                name="summary_namespace_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(
                fields=["node"],
                name="summary_node_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(fields=["data_source"], name="summary_data_source_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=django.contrib.postgres.indexes.GinIndex(fields=["pod_labels"], name="pod_labels_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(fields=["monthly_cost_type"], name="monthly_cost_type_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="ocpstoragevolumelabelsummary",
            unique_together={("key", "report_period", "namespace", "node")},
        ),
        migrations.AddIndex(
            model_name="ocpstoragevolumelabelsummary",
            index=models.Index(fields=["key"], name="openshift_vol_label_key_idx"),
        ),
        migrations.AddIndex(
            model_name="ocppodsummaryp",
            index=models.Index(fields=["usage_start"], name="ocppodsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocppodsummarybyprojectp",
            index=models.Index(fields=["usage_start"], name="ocppodsumm_proj_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocppodsummarybyprojectp",
            index=models.Index(fields=["namespace"], name="ocppodsumm_proj_namespace"),
        ),
        migrations.AlterUniqueTogether(
            name="ocpgcptagssummary",
            unique_together={
                (
                    "key",
                    "cost_entry_bill",
                    "account_id",
                    "project_id",
                    "project_name",
                    "report_period",
                    "namespace",
                    "node",
                )
            },
        ),
        migrations.AddIndex(
            model_name="ocpgcpstoragesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcpstorage_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpnetworksummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcpnetwork_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpdatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcpdb_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcpcostsum_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="ocpgcpcostsum_serv_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyservicep",
            index=models.Index(fields=["service_id"], name="ocpgcpcostsum_servid_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyservicep",
            index=models.Index(fields=["service_alias"], name="ocpgcpcostsum_servalias_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyregionp",
            index=models.Index(fields=["usage_start"], name="ocpgcpcostsum_reg_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyregionp",
            index=models.Index(fields=["region"], name="ocpgcpcostsum_reg_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybygcpprojectp",
            index=models.Index(fields=["usage_start"], name="ocpgcpcostsum_gcpp_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybygcpprojectp",
            index=models.Index(fields=["project_id"], name="ocpgcpcostsum_gcpp_projid_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybygcpprojectp",
            index=models.Index(fields=["project_name"], name="ocpgcpcostsum_gcpp_projn_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="ocpgcpcostsum_acct_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostsummarybyaccountp",
            index=models.Index(fields=["account_id"], name="ocpgcpcostsum_acct_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcp_proj_usage_start_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["namespace"], name="ocpgcp_proj_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="ocpgcp_proj_node_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["resource_id"], name="ocpgcp_proj_resource_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="ocpgcp_proj_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["project_id"], name="ocpgcp_proj_id_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["project_name"], name="ocpgcp_proj_name_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["service_id"], name="ocpgcp_proj_service_id_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["service_alias"], name="ocpgcp_proj_service_alias_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcp_usage_start_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["namespace"], name="ocpgcp_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="ocpgcp_node_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["resource_id"], name="ocpgcp_resource_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="ocpgcp_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["project_id"], name="ocpgcp_id_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["project_name"], name="ocpgcp_name_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["service_id"], name="ocpgcp_service_id_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcostlineitemdailysummaryp",
            index=models.Index(fields=["service_alias"], name="ocpgcp_service_alias_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpgcpcomputesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpgcpcompute_usgstrt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummaryp",
            index=models.Index(fields=["usage_start"], name="ocpcostsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybyprojectp",
            index=models.Index(fields=["usage_start"], name="ocpcostsumm_proj_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybyprojectp",
            index=models.Index(fields=["namespace"], name="ocpcostsumm_proj_namespace"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybynodep",
            index=models.Index(fields=["usage_start"], name="ocpcostsumm_node_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpcostsummarybynodep",
            index=models.Index(fields=["node"], name="ocpcostsumm_node_node"),
        ),
        migrations.AlterUniqueTogether(
            name="ocpazuretagssummary",
            unique_together={
                (
                    "key",
                    "cost_entry_bill",
                    "report_period",
                    "subscription_guid",
                    "namespace",
                    "node",
                )
            },
        ),
        migrations.AddIndex(
            model_name="ocpazurestoragesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpazstorsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazurestoragesummaryp",
            index=models.Index(fields=["service_name"], name="ocpazstorsumm_svc_name"),
        ),
        migrations.AddIndex(
            model_name="ocpazurestoragesummaryp",
            index=models.Index(fields=["cluster_id"], name="ocpazstorsumm_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazurenetworksummaryp",
            index=models.Index(fields=["usage_start"], name="ocpaznetsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazurenetworksummaryp",
            index=models.Index(fields=["service_name"], name="ocpaznetsumm_svc_name"),
        ),
        migrations.AddIndex(
            model_name="ocpazurenetworksummaryp",
            index=models.Index(fields=["cluster_id"], name="ocpaznetsumm_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazuredatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpazdbsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazuredatabasesummaryp",
            index=models.Index(fields=["service_name"], name="ocpazdbsumm_svc_name"),
        ),
        migrations.AddIndex(
            model_name="ocpazuredatabasesummaryp",
            index=models.Index(fields=["cluster_id"], name="ocpazdbsumm_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummaryp",
            index=models.Index(fields=["cluster_id"], name="ocpazcostsumm_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="ocpazcostsumm_svc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybyservicep",
            index=models.Index(fields=["service_name"], name="ocpazcostsumm_svc_svc_name"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybyservicep",
            index=models.Index(fields=["cluster_id"], name="ocpazcostsumm_svc_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybylocationp",
            index=models.Index(fields=["usage_start"], name="ocpazcostsumm_loc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybylocationp",
            index=models.Index(fields=["resource_location"], name="ocpazcostsumm_loc_res_loc"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybylocationp",
            index=models.Index(fields=["cluster_id"], name="ocpazcostsumm_loc_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="ocpazcostsumm_acc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybyaccountp",
            index=models.Index(fields=["subscription_guid"], name="ocpazcostsumm_acc_sub_guid"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostsummarybyaccountp",
            index=models.Index(fields=["cluster_id"], name="ocpazcostsumm_acc_clust_id"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=models.Index(fields=["usage_start"], name="p_ocpaz_prj_use_strt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=models.Index(
                fields=["namespace"],
                name="p_ocpaz_prj_nspc_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="p_ocpaz_prj_nde_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=models.Index(fields=["resource_id"], name="p_ocpaz_prj_rsrc_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["pod_labels"], name="p_ocpaz_prj_pod_lbl_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=models.Index(fields=["service_name"], name="p_ocpaz_prj_srvc_name_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            index=models.Index(fields=["instance_type"], name="p_ocpaz_prj_inst_typ_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=models.Index(fields=["usage_start"], name="p_ocpaz_use_strt_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=models.Index(fields=["namespace"], name="p_ocpaz_nspc_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="p_ocpaz_nde_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=models.Index(fields=["resource_id"], name="p_ocpaz_rsrc_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="p_ocpaz_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=models.Index(fields=["service_name"], name="p_ocpaz_svc_name_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecostlineitemdailysummaryp",
            index=models.Index(fields=["instance_type"], name="p_ocpaz_inst_typ_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecomputesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpazcompsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecomputesummaryp",
            index=models.Index(fields=["instance_type"], name="ocpazcompsumm_insttyp"),
        ),
        migrations.AddIndex(
            model_name="ocpazurecomputesummaryp",
            index=models.Index(fields=["cluster_id"], name="ocpazcompsumm_clust_id"),
        ),
        migrations.AlterUniqueTogether(
            name="ocpawstagssummary",
            unique_together={
                (
                    "key",
                    "cost_entry_bill",
                    "report_period",
                    "usage_account_id",
                    "namespace",
                    "node",
                )
            },
        ),
        migrations.AddIndex(
            model_name="ocpawsstoragesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpawsstorsumm_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawsstoragesummaryp",
            index=models.Index(fields=["product_family"], name="ocpawsstorsumm_product_fam"),
        ),
        migrations.AddIndex(
            model_name="ocpawsnetworksummaryp",
            index=models.Index(fields=["usage_start"], name="ocpawsnetsumm_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawsnetworksummaryp",
            index=models.Index(fields=["product_code"], name="ocpawsnetsumm_product_cd"),
        ),
        migrations.AddIndex(
            model_name="ocpawsdatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpawsdbsumm_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawsdatabasesummaryp",
            index=models.Index(fields=["product_code"], name="ocpawsdbsumm_product_cd"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummaryp",
            index=models.Index(fields=["usage_start"], name="ocpawscostsumm_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="ocpawscostsumm_svc_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummarybyservicep",
            index=models.Index(fields=["product_code"], name="ocpawscostsumm_svc_prod_cd"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummarybyregionp",
            index=models.Index(fields=["usage_start"], name="ocpawscostsumm_reg_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummarybyregionp",
            index=models.Index(fields=["region"], name="ocpawscostsumm_reg_region"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummarybyregionp",
            index=models.Index(fields=["availability_zone"], name="ocpawscostsumm_reg_zone"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="ocpawscostsumm_acct_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=models.Index(fields=["usage_start"], name="p_cost_prj_sum_ocp_use_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=models.Index(
                fields=["namespace"],
                name="p_cost_prj_sum_nspc_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="p_cost_prj_sum_nd_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=models.Index(fields=["resource_id"], name="p_cost_prj_sum_rsrc_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["pod_labels"], name="p_cost_prj_pod_lbls_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=models.Index(fields=["product_family"], name="p_ocpaws_prj_prd_fam_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=models.Index(fields=["instance_type"], name="p_ocpaws_prj_inst_typ_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=models.Index(fields=["usage_start"], name="p_cost_sum_ocpaws_use_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=models.Index(fields=["namespace"], name="p_cost_sum_ocpaws_nspc_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="p_cost_sum_ocpaws_nde_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=models.Index(fields=["resource_id"], name="p_cost_sum_ocpaws_rsrc_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="p_cost_ocpaws_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=models.Index(fields=["product_family"], name="p_ocpaws_prod_fam_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemdailysummaryp",
            index=models.Index(fields=["instance_type"], name="p_ocpaws_inst_typ_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscomputesummaryp",
            index=models.Index(fields=["usage_start"], name="ocpawscompsumm_usst"),
        ),
        migrations.AddIndex(
            model_name="ocpawscomputesummaryp",
            index=models.Index(fields=["instance_type"], name="ocpawscompsumm_insttyp"),
        ),
        migrations.AddIndex(
            model_name="ocpallstoragesummarypt",
            index=models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_stor_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallstoragesummarypt",
            index=models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_stor_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallstoragesummarypt",
            index=models.Index(fields=["product_code"], name="ocpap_cmpsumm_stor_procode_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallstoragesummarypt",
            index=models.Index(fields=["product_family"], name="ocpap_cmpsumm_stor_profam_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallnetworksummarypt",
            index=models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_net_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallnetworksummarypt",
            index=models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_net_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallnetworksummarypt",
            index=models.Index(fields=["product_code"], name="ocpap_cmpsumm_net_procode_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpalldatabasesummarypt",
            index=models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_db_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpalldatabasesummarypt",
            index=models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_db_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpalldatabasesummarypt",
            index=models.Index(fields=["product_code"], name="ocpap_cmpsumm_db_procode_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarypt",
            index=models.Index(fields=["cluster_id"], name="ocpap_costsumm_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyservicept",
            index=models.Index(fields=["cluster_id"], name="ocpap_costsumm_srv_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyservicept",
            index=models.Index(fields=["usage_account_id"], name="ocpap_costsumm_srv_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyservicept",
            index=models.Index(fields=["product_code"], name="ocpap_costsumm_srv_procode_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyservicept",
            index=models.Index(fields=["product_family"], name="ocpap_costsumm_srv_profam_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyregionpt",
            index=models.Index(fields=["cluster_id"], name="ocpap_costsumm_rgn_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyregionpt",
            index=models.Index(fields=["usage_account_id"], name="ocpap_costsumm_rgn_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyregionpt",
            index=models.Index(fields=["region"], name="ocpap_costsumm_rgn_region_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyregionpt",
            index=models.Index(fields=["availability_zone"], name="ocpap_costsumm_rgn_avail_zn_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyaccountpt",
            index=models.Index(fields=["cluster_id"], name="ocpap_costsumm_acct_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostsummarybyaccountpt",
            index=models.Index(fields=["usage_account_id"], name="ocpap_costsumm_acct_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["usage_start"], name="ocpap_p_proj_usage_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["namespace"], name="ocpap_p_proj_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["node"], name="ocpap_p_proj_node_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["resource_id"], name="ocpap_p_proj_resource_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["pod_labels"], name="ocpap_p_proj_pod_labels_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["product_family"], name="ocpap_p_proj_prod_fam_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            index=models.Index(fields=["instance_type"], name="ocpap_p_proj_inst_type_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=models.Index(fields=["usage_start"], name="ocpall_p_usage_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=models.Index(fields=["namespace"], name="ocpall_p_namespace_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=models.Index(
                fields=["node"],
                name="ocpall_p_node_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=models.Index(fields=["resource_id"], name="ocpall_p_resource_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="ocpall_p_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=models.Index(fields=["product_family"], name="ocpall_p_product_family_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcostlineitemdailysummaryp",
            index=models.Index(fields=["instance_type"], name="ocpall_p_instance_type_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpallcomputesummarypt",
            index=models.Index(fields=["cluster_id"], name="ocpap_cmpsumm_clust_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcomputesummarypt",
            index=models.Index(fields=["usage_account_id"], name="ocpap_cmpsumm_acctid_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcomputesummarypt",
            index=models.Index(fields=["product_code"], name="ocpap_cmpsumm_procode_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcomputesummarypt",
            index=models.Index(fields=["instance_type"], name="ocpap_cmpsumm_inst_typ_ix"),
        ),
        migrations.AddIndex(
            model_name="ocpallcomputesummarypt",
            index=models.Index(fields=["resource_id"], name="ocpap_cmpsumm_rsrc_id_ix"),
        ),
        migrations.AlterUniqueTogether(
            name="gcptagssummary",
            unique_together={("key", "cost_entry_bill", "account_id", "project_id", "project_name")},
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummaryp",
            index=models.Index(fields=["usage_start"], name="gcpstorsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummaryp",
            index=models.Index(fields=["invoice_month"], name="gcpstorsumm_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyservicep",
            index=models.Index(fields=["usage_start"], name="gcpstorsumm_ser_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyservicep",
            index=models.Index(fields=["service_id"], name="gcpstorsumm_ser_service_id"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyservicep",
            index=models.Index(fields=["account_id"], name="gcpstorsumm_ser_account_id"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyservicep",
            index=models.Index(fields=["invoice_month"], name="gcpstorsumm_ser_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyregionp",
            index=models.Index(fields=["usage_start"], name="gcpstorsumm_reg_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyregionp",
            index=models.Index(fields=["account_id"], name="gcpstorsumm_reg_account_id"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyregionp",
            index=models.Index(fields=["invoice_month"], name="gcpstorsumm_reg_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyprojectp",
            index=models.Index(fields=["usage_start"], name="gcpstorsumm_pro_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyprojectp",
            index=models.Index(fields=["project_id"], name="gcpstorsumm_pro_project_id"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyprojectp",
            index=models.Index(fields=["account_id"], name="gcpstorsumm_pro_account_id"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyprojectp",
            index=models.Index(fields=["invoice_month"], name="gcpstorsumm_pro_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="gcpstorsumm_acc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyaccountp",
            index=models.Index(fields=["account_id"], name="gcpstorsumm_acc_account_id"),
        ),
        migrations.AddIndex(
            model_name="gcpstoragesummarybyaccountp",
            index=models.Index(fields=["invoice_month"], name="gcpstorsumm_acc_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpnetworksummaryp",
            index=models.Index(fields=["usage_start"], name="gcpnetsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpnetworksummaryp",
            index=models.Index(fields=["invoice_month"], name="gcpnetsumm_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpdatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="gcpdbsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpdatabasesummaryp",
            index=models.Index(fields=["invoice_month"], name="gcpdbsumm_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummaryp",
            index=models.Index(fields=["usage_start"], name="gcpcostsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummaryp",
            index=models.Index(fields=["invoice_month"], name="gcpcostsumm_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="gcpcostsumm_ser_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyservicep",
            index=models.Index(fields=["service_id"], name="gcpcostsumm_ser_service_id"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyservicep",
            index=models.Index(fields=["invoice_month"], name="gcpcostsumm_ser_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyregionp",
            index=models.Index(fields=["usage_start"], name="gcpcostsumm_reg_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyregionp",
            index=models.Index(fields=["region"], name="gcpcostsumm_reg_region"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyregionp",
            index=models.Index(fields=["invoice_month"], name="gcpcostsumm_reg_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyprojectp",
            index=models.Index(fields=["usage_start"], name="gcpcostsumm_pro_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyprojectp",
            index=models.Index(fields=["project_id"], name="gcpcostsumm_pro_project_id"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyprojectp",
            index=models.Index(fields=["invoice_month"], name="gcpcostsumm_pro_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="gcpcostsumm_acc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyaccountp",
            index=models.Index(fields=["account_id"], name="gcpcostsumm_acc_account_id"),
        ),
        migrations.AddIndex(
            model_name="gcpcostsummarybyaccountp",
            index=models.Index(fields=["invoice_month"], name="gcpcostsumm_acc_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=models.Index(fields=["usage_start"], name="gcp_summary_usage_start_idx"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=models.Index(fields=["instance_type"], name="gcp_summary_instance_type_idx"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="gcp_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=models.Index(fields=["project_id"], name="gcp_summary_project_id_idx"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=models.Index(fields=["project_name"], name="gcp_summary_project_name_idx"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=models.Index(fields=["service_id"], name="gcp_summary_service_id_idx"),
        ),
        migrations.AddIndex(
            model_name="gcpcostentrylineitemdailysummary",
            index=models.Index(fields=["service_alias"], name="gcp_summary_service_alias_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="gcpcostentrybill",
            unique_together={("billing_period_start", "provider")},
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummaryp",
            index=models.Index(fields=["usage_start"], name="gcpcompsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummaryp",
            index=models.Index(fields=["instance_type"], name="gcpcompsumm_insttyp"),
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummaryp",
            index=models.Index(fields=["invoice_month"], name="gcpcompsumm_invmonth"),
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummarybyaccountp",
            index=models.Index(fields=["account_id"], name="gcpcompsumm_acc_account_id"),
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="gcpcompsumm_acc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummarybyaccountp",
            index=models.Index(fields=["instance_type"], name="gcpcompsumm_acc_insttyp"),
        ),
        migrations.AddIndex(
            model_name="gcpcomputesummarybyaccountp",
            index=models.Index(fields=["invoice_month"], name="gcpcompsumm_acc_invmonth"),
        ),
        migrations.AddIndex(
            model_name="costsummary",
            index=models.Index(fields=["usage_start"], name="ocpcostsum_usage_start_idx"),
        ),
        migrations.AddIndex(
            model_name="costsummary",
            index=models.Index(
                fields=["namespace"],
                name="ocpcostsum_namespace_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="costsummary",
            index=models.Index(
                fields=["node"],
                name="ocpcostsum_node_idx",
                opclasses=["varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="costsummary",
            index=django.contrib.postgres.indexes.GinIndex(fields=["pod_labels"], name="ocpcostsum_pod_labels_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="azuretagssummary",
            unique_together={("key", "cost_entry_bill", "subscription_guid")},
        ),
        migrations.AddIndex(
            model_name="azurestoragesummaryp",
            index=models.Index(fields=["usage_start"], name="azurestorsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurestoragesummaryp",
            index=models.Index(fields=["service_name"], name="azurestorsumm_svc_name"),
        ),
        migrations.AddIndex(
            model_name="azurenetworksummaryp",
            index=models.Index(fields=["usage_start"], name="azurenetsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurenetworksummaryp",
            index=models.Index(fields=["service_name"], name="azurenetsumm_svc_name"),
        ),
        migrations.AddIndex(
            model_name="azuredatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="azuredbsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azuredatabasesummaryp",
            index=models.Index(fields=["service_name"], name="azuredbsumm_svc_name"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummaryp",
            index=models.Index(fields=["usage_start"], name="azurecostsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="azurecostsumm_svc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybyservicep",
            index=models.Index(fields=["service_name"], name="azurecostsumm_svc_svc_name"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybylocationp",
            index=models.Index(fields=["usage_start"], name="azurecostsumm_loc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybylocationp",
            index=models.Index(fields=["resource_location"], name="azurecostsumm_loc_res_loc"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="azurecostsumm_acc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybyaccountp",
            index=models.Index(fields=["subscription_guid"], name="azurecostsumm_acc_sub_guid"),
        ),
        migrations.AddIndex(
            model_name="azurecostentrylineitemdailysummary",
            index=models.Index(fields=["usage_start"], name="ix_azurecstentrydlysumm_start"),
        ),
        migrations.AlterUniqueTogether(
            name="azurecostentrybill",
            unique_together={("billing_period_start", "provider")},
        ),
        migrations.AddIndex(
            model_name="azurecomputesummaryp",
            index=models.Index(fields=["usage_start"], name="azurecompsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="azurecomputesummaryp",
            index=models.Index(fields=["instance_type"], name="azurecompsumm_insttyp"),
        ),
        migrations.AlterUniqueTogether(
            name="awstagssummary",
            unique_together={("key", "cost_entry_bill", "usage_account_id")},
        ),
        migrations.AddIndex(
            model_name="awsstoragesummaryp",
            index=models.Index(fields=["usage_start"], name="awsstorsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awsstoragesummaryp",
            index=models.Index(fields=["product_family"], name="awsstorsumm_product_fam"),
        ),
        migrations.AddIndex(
            model_name="awsstoragesummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="awsstorsumm_acct_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awsstoragesummarybyaccountp",
            index=models.Index(fields=["product_family"], name="awsstorsumm_product_acct_fam"),
        ),
        migrations.AddIndex(
            model_name="awsnetworksummaryp",
            index=models.Index(fields=["usage_start"], name="awsnetsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awsnetworksummaryp",
            index=models.Index(fields=["product_code"], name="awsnetsumm_product_cd"),
        ),
        migrations.AddIndex(
            model_name="awsdatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="awsdbsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awsdatabasesummaryp",
            index=models.Index(fields=["product_code"], name="awsdbsumm_product_cd"),
        ),
        migrations.AddIndex(
            model_name="awscostsummaryp",
            index=models.Index(fields=["usage_start"], name="awscostsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awscostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="awscostsumm_svc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awscostsummarybyservicep",
            index=models.Index(fields=["product_code"], name="awscostsumm_svc_prod_cd"),
        ),
        migrations.AddIndex(
            model_name="awscostsummarybyregionp",
            index=models.Index(fields=["usage_start"], name="awscostsumm_reg_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awscostsummarybyregionp",
            index=models.Index(fields=["region"], name="awscostsumm_reg_region"),
        ),
        migrations.AddIndex(
            model_name="awscostsummarybyregionp",
            index=models.Index(fields=["availability_zone"], name="awscostsumm_reg_zone"),
        ),
        migrations.AddIndex(
            model_name="awscostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="awscostsumm_acct_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["usage_start"], name="summary_usage_start_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["product_code"], name="summary_product_code_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["usage_account_id"], name="summary_usage_account_id_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="tags_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["account_alias"], name="summary_account_alias_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["product_family"], name="summary_product_family_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["instance_type"], name="summary_instance_type_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="awscostentrybill",
            unique_together={("bill_type", "payer_account_id", "billing_period_start", "provider")},
        ),
        migrations.AddIndex(
            model_name="awscomputesummaryp",
            index=models.Index(fields=["usage_start"], name="awscompsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awscomputesummaryp",
            index=models.Index(fields=["instance_type"], name="awscompsumm_insttyp"),
        ),
        migrations.AddIndex(
            model_name="awscomputesummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="awscompsumm_acct_usage_start"),
        ),
        migrations.AddIndex(
            model_name="awscomputesummarybyaccountp",
            index=models.Index(fields=["instance_type"], name="awscompsumm_acct_insttyp"),
        ),
        migrations.AlterUniqueTogether(
            name="ocitagssummary",
            unique_together={("key", "cost_entry_bill", "payer_tenant_id")},
        ),
        migrations.AddIndex(
            model_name="ocistoragesummaryp",
            index=models.Index(fields=["usage_start"], name="ocistorsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocistoragesummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="ocistorsumm_acct_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocinetworksummaryp",
            index=models.Index(fields=["usage_start"], name="ocinetsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocinetworksummaryp",
            index=models.Index(fields=["product_service"], name="ocinetsumm_product_cd"),
        ),
        migrations.AddIndex(
            model_name="ocidatabasesummaryp",
            index=models.Index(fields=["usage_start"], name="ocidbsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocidatabasesummaryp",
            index=models.Index(fields=["product_service"], name="ocidbsumm_product_cd"),
        ),
        migrations.AddIndex(
            model_name="ocicostsummaryp",
            index=models.Index(fields=["usage_start"], name="ocicostsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocicostsummarybyservicep",
            index=models.Index(fields=["usage_start"], name="ocicostsumm_svc_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocicostsummarybyservicep",
            index=models.Index(fields=["product_service"], name="ocicostsumm_svc_prod_cd"),
        ),
        migrations.AddIndex(
            model_name="ocicostsummarybyregionp",
            index=models.Index(fields=["usage_start"], name="ocicostsumm_reg_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocicostsummarybyregionp",
            index=models.Index(fields=["region"], name="ocicostsumm_reg_region"),
        ),
        migrations.AddIndex(
            model_name="ocicostsummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="ocicostsumm_acct_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocicostentrylineitemdailysummary",
            index=models.Index(fields=["usage_start"], name="summary_oci_usage_start_idx"),
        ),
        migrations.AddIndex(
            model_name="ocicostentrylineitemdailysummary",
            index=models.Index(fields=["product_service"], name="summary_oci_product_code_idx"),
        ),
        migrations.AddIndex(
            model_name="ocicostentrylineitemdailysummary",
            index=models.Index(fields=["payer_tenant_id"], name="summary_oci_payer_tenant_idx"),
        ),
        migrations.AddIndex(
            model_name="ocicostentrylineitemdailysummary",
            index=django.contrib.postgres.indexes.GinIndex(fields=["tags"], name="tags_tags_idx"),
        ),
        migrations.AddIndex(
            model_name="ocicostentrylineitemdailysummary",
            index=models.Index(fields=["instance_type"], name="summary_oci_instance_type_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="ocicostentrybill",
            unique_together={("bill_type", "payer_tenant_id", "billing_period_start", "provider")},
        ),
        migrations.AddIndex(
            model_name="ocicomputesummaryp",
            index=models.Index(fields=["usage_start"], name="ocicompsumm_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocicomputesummaryp",
            index=models.Index(fields=["instance_type"], name="ocicompsumm_insttyp"),
        ),
        migrations.AddIndex(
            model_name="ocicomputesummarybyaccountp",
            index=models.Index(fields=["usage_start"], name="ocicompsumm_acct_usage_start"),
        ),
        migrations.AddIndex(
            model_name="ocicomputesummarybyaccountp",
            index=models.Index(fields=["instance_type"], name="ocicompsumm_acct_insttyp"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["region"], name="summary_region_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=models.Index(fields=["availability_zone"], name="summary_zone_idx"),
        ),
        migrations.AddIndex(
            model_name="azurecostentrylineitemdailysummary",
            index=models.Index(fields=["resource_location"], name="ix_azurecstentrydlysumm_svc"),
        ),
        migrations.AddIndex(
            model_name="azurecostentrylineitemdailysummary",
            index=models.Index(fields=["subscription_guid"], name="ix_azurecstentrydlysumm_sub_id"),
        ),
        migrations.AddIndex(
            model_name="azurecostentrylineitemdailysummary",
            index=models.Index(fields=["instance_type"], name="ix_azurecstentrydlysumm_instyp"),
        ),
        migrations.AddIndex(
            model_name="ocpusagelineitemdailysummary",
            index=models.Index(fields=["cost_model_rate_type"], name="cost_model_rate_type_idx"),
        ),
        migrations.AddIndex(
            model_name="awscostentrylineitemdailysummary",
            index=django.contrib.postgres.indexes.GinIndex(fields=["cost_category"], name="cost_category_idx"),
        ),
        migrations.AddIndex(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            index=django.contrib.postgres.indexes.GinIndex(fields=["aws_cost_category"], name="aws_cost_category_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="ocpcluster",
            unique_together={("cluster_id", "cluster_alias", "provider")},
        ),
        migrations.AlterUniqueTogether(
            name="ocpproject",
            unique_together={("project", "cluster")},
        ),
        migrations.AlterUniqueTogether(
            name="ocppvc",
            unique_together={("persistent_volume", "persistent_volume_claim", "cluster")},
        ),
        migrations.AddIndex(
            model_name="azurecostentrylineitemdailysummary",
            index=models.Index(fields=["subscription_name"], name="ix_azurecstentrydlysumm_sub_na"),
        ),
        migrations.AddIndex(
            model_name="azurecostsummarybyaccountp",
            index=models.Index(fields=["subscription_name"], name="azurecostsumm_acc_sub_name"),
        ),
        migrations.RunPython(code=unset_pg_extended_mode, reverse_code=set_pg_extended_mode),
    ]
