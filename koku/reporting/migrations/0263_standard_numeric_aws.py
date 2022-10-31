from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0262_standard_numeric_on_calculated_feilds"),
    ]

    operations = [
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_compute_summary_by_account_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscomputesummarybyaccountp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummarybyaccountp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummarybyaccountp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_compute_summary_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscomputesummaryp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummaryp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscomputesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_awscostentrylineitem
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN blended_rate TYPE numeric(33, 15),
                    ALTER COLUMN normalized_usage_amount TYPE numeric(33, 15),
                    ALTER COLUMN public_on_demand_cost TYPE numeric(33, 15),
                    ALTER COLUMN public_on_demand_rate TYPE numeric(33, 15),
                    ALTER COLUMN reservation_amortized_upfront_cost_for_usage TYPE numeric(33, 15),
                    ALTER COLUMN reservation_amortized_upfront_fee TYPE numeric(33, 15),
                    ALTER COLUMN reservation_recurring_fee_for_usage TYPE numeric(33, 15),
                    ALTER COLUMN reservation_unused_quantity TYPE numeric(33, 15),
                    ALTER COLUMN reservation_unused_recurring_fee TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_rate TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)

            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="blended_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="normalized_usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="public_on_demand_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="public_on_demand_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="reservation_amortized_upfront_cost_for_usage",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="reservation_amortized_upfront_fee",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="reservation_recurring_fee_for_usage",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="reservation_unused_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="reservation_unused_recurring_fee",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="unblended_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitem",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_awscostentrylineitem_daily
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN blended_rate TYPE numeric(33, 15),
                    ALTER COLUMN public_on_demand_cost TYPE numeric(33, 15),
                    ALTER COLUMN public_on_demand_rate TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_rate TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="blended_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="public_on_demand_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="public_on_demand_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="unblended_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdaily",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_awscostentrylineitem_daily_summary
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN blended_rate TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN public_on_demand_cost TYPE numeric(33, 15),
                    ALTER COLUMN public_on_demand_rate TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_rate TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="blended_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="public_on_demand_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="public_on_demand_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="unblended_rate",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostentrylineitemdailysummary",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_awscostentryreservation
                    ALTER COLUMN units_per_reservation TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostentryreservation",
                    name="units_per_reservation",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_cost_summary_by_account_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostsummarybyaccountp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyaccountp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_cost_summary_by_region_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostsummarybyregionp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyregionp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyregionp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyregionp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_cost_summary_by_service_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostsummarybyservicep",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyservicep",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyservicep",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummarybyservicep",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_cost_summary_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awscostsummaryp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummaryp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awscostsummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_database_summary_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awsdatabasesummaryp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsdatabasesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsdatabasesummaryp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsdatabasesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsdatabasesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_network_summary_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awsnetworksummaryp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsnetworksummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsnetworksummaryp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsnetworksummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsnetworksummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_storage_summary_by_account_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awsstoragesummarybyaccountp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummarybyaccountp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummarybyaccountp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_aws_storage_summary_p
                    ALTER COLUMN blended_cost TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN savingsplan_effective_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="awsstoragesummaryp",
                    name="blended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummaryp",
                    name="savingsplan_effective_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="awsstoragesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
    ]
