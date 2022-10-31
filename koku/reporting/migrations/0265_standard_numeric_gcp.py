from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0264_standard_numeric_azure"),
    ]

    operations = [
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_compute_summary_by_account_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcomputesummarybyaccountp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcomputesummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcomputesummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcomputesummarybyaccountp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_compute_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcomputesummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcomputesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcomputesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcomputesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcpcostentrylineitem
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_to_pricing_units TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostentrylineitem",
                    name="cost",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostentrylineitem",
                    name="usage_to_pricing_units",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcpcostentrylineitem_daily
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN usage_in_pricing_units TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdaily",
                    name="cost",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdaily",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdaily",
                    name="usage_in_pricing_units",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcpcostentrylineitem_daily_summary
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdailysummary",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdailysummary",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdailysummary",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostentrylineitemdailysummary",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_cost_summary_by_account_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostsummarybyaccountp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_cost_summary_by_project_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostsummarybyprojectp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyprojectp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyprojectp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_cost_summary_by_region_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostsummarybyregionp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyregionp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyregionp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_cost_summary_by_service_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostsummarybyservicep",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyservicep",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummarybyservicep",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_cost_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpcostsummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpcostsummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_database_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpdatabasesummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpdatabasesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpdatabasesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpdatabasesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_network_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpnetworksummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpnetworksummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpnetworksummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpnetworksummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_storage_summary_by_account_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpstoragesummarybyaccountp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyaccountp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_storage_summary_by_project_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpstoragesummarybyprojectp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyprojectp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyprojectp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyprojectp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_storage_summary_by_region_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpstoragesummarybyregionp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyregionp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyregionp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyregionp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_storage_summary_by_service_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpstoragesummarybyservicep",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyservicep",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyservicep",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummarybyservicep",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_gcp_storage_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="gcpstoragesummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="gcpstoragesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        )
    ]