from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0266_standard_numeric_oci"),
    ]

    operations = [
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpcosts_summary
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN project_markup_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="costsummary",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="costsummary",
                    name="project_markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_compute_summary_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcomputesummarypt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcomputesummarypt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcomputesummarypt",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpallcostlineitem_daily_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcostlineitemdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostlineitemdailysummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostlineitemdailysummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpallcostlineitem_project_daily_summary_p
                    ALTER COLUMN pod_cost TYPE numeric(33, 15),
                    ALTER COLUMN project_markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcostlineitemprojectdailysummaryp",
                    name="pod_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostlineitemprojectdailysummaryp",
                    name="project_markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostlineitemprojectdailysummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostlineitemprojectdailysummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_cost_summary_by_account_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcostsummarybyaccountpt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostsummarybyaccountpt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_cost_summary_by_region_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcostsummarybyregionpt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostsummarybyregionpt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_cost_summary_by_service_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcostsummarybyservicept",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostsummarybyservicept",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_cost_summary_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallcostsummarypt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallcostsummarypt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_database_summary_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpalldatabasesummarypt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpalldatabasesummarypt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpalldatabasesummarypt",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_network_summary_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallnetworksummarypt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallnetworksummarypt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallnetworksummarypt",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpall_storage_summary_pt
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpallstoragesummarypt",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallstoragesummarypt",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpallstoragesummarypt",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpawscostlineitem_daily_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpawscostlineitemdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpawscostlineitemdailysummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpawscostlineitemdailysummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpawscostlineitem_project_daily_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pod_cost TYPE numeric(33, 15),
                    ALTER COLUMN project_markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpawscostlineitemprojectdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpawscostlineitemprojectdailysummaryp",
                    name="pod_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpawscostlineitemprojectdailysummaryp",
                    name="project_markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpawscostlineitemprojectdailysummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpawscostlineitemprojectdailysummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpazurecostlineitem_daily_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpazurecostlineitemdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpazurecostlineitemdailysummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpazurecostlineitemdailysummaryp",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpazurecostlineitem_project_daily_summary_p
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pod_cost TYPE numeric(33, 15),
                    ALTER COLUMN pretax_cost TYPE numeric(33, 15),
                    ALTER COLUMN project_markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_quantity TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpazurecostlineitemprojectdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpazurecostlineitemprojectdailysummaryp",
                    name="pod_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpazurecostlineitemprojectdailysummaryp",
                    name="pretax_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpazurecostlineitemprojectdailysummaryp",
                    name="project_markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpazurecostlineitemprojectdailysummaryp",
                    name="usage_quantity",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_compute_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcomputesummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcomputesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcomputesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcomputesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcpcostlineitem_daily_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemdailysummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemdailysummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemdailysummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcpcostlineitem_project_daily_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN pod_cost TYPE numeric(33, 15),
                    ALTER COLUMN project_markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemprojectdailysummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemprojectdailysummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemprojectdailysummaryp",
                    name="pod_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemprojectdailysummaryp",
                    name="project_markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemprojectdailysummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostlineitemprojectdailysummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_cost_summary_by_account_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyaccountp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyaccountp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyaccountp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_cost_summary_by_gcp_project_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybygcpprojectp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybygcpprojectp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybygcpprojectp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_cost_summary_by_region_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyregionp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyregionp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyregionp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_cost_summary_by_service_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyservicep",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyservicep",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummarybyservicep",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_cost_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpcostsummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpcostsummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_database_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpdatabasesummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpdatabasesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpdatabasesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpdatabasesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_network_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpnetworksummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpnetworksummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpnetworksummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpnetworksummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
        migrations.RunSQL(
            """
                ALTER TABLE reporting_ocpgcp_storage_summary_p
                    ALTER COLUMN credit_amount TYPE numeric(33, 15),
                    ALTER COLUMN markup_cost TYPE numeric(33, 15),
                    ALTER COLUMN unblended_cost TYPE numeric(33, 15),
                    ALTER COLUMN usage_amount TYPE numeric(33, 15)
            """,
            state_operations=[
                migrations.AlterField(
                    model_name="ocpgcpstoragesummaryp",
                    name="credit_amount",
                    field=models.DecimalField(blank=True, decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpstoragesummaryp",
                    name="markup_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpstoragesummaryp",
                    name="unblended_cost",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
                migrations.AlterField(
                    model_name="ocpgcpstoragesummaryp",
                    name="usage_amount",
                    field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
                ),
            ],
        ),
    ]
