from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0263_standard_numeric_aws"),
    ]

    operations = [
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_compute_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecomputesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecomputesummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecomputesummaryp",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azurecostentrylineitem_daily
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecostentrylineitemdaily",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostentrylineitemdaily",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azurecostentrylineitem_daily_summary
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecostentrylineitemdailysummary",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostentrylineitemdailysummary",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostentrylineitemdailysummary",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_cost_summary_by_account_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecostsummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostsummarybyaccountp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_cost_summary_by_location_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecostsummarybylocationp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostsummarybylocationp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_cost_summary_by_service_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecostsummarybyservicep",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostsummarybyservicep",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_cost_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurecostsummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurecostsummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_database_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azuredatabasesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azuredatabasesummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azuredatabasesummaryp",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_network_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurenetworksummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurenetworksummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurenetworksummaryp",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_azure_storage_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="azurestoragesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurestoragesummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="azurestoragesummaryp",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        )
    ]