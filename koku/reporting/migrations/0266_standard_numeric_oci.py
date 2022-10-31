from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0265_standard_numeric_gcp"),
    ]

    operations = [
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_compute_summary_by_account_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicomputesummarybyaccountp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicomputesummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicomputesummarybyaccountp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_compute_summary_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicomputesummaryp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicomputesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicomputesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocicostentrylineitem_daily_summary
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicostentrylineitemdailysummary",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicostentrylineitemdailysummary",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicostentrylineitemdailysummary",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_cost_summary_by_account_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicostsummarybyaccountp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicostsummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_cost_summary_by_region_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicostsummarybyregionp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicostsummarybyregionp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_cost_summary_by_service_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicostsummarybyservicep",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicostsummarybyservicep",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_cost_summary_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocicostsummaryp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocicostsummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_database_summary_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocidatabasesummaryp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocidatabasesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocidatabasesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_network_summary_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocinetworksummaryp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocinetworksummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocinetworksummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_storage_summary_by_account_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocistoragesummarybyaccountp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocistoragesummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocistoragesummarybyaccountp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_oci_storage_summary_p
                    ALTER COLUMN cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocistoragesummaryp",
                    name="cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocistoragesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocistoragesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
    ]
