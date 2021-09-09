from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("reporting", "001_initial.py")]  # definitely will need to edit this line

    operations = [
        migrations.RunSQL(
            "ALTER TABLE reporting_aws_cost_summary ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_cost_summary",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_cost_summary_by_service ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_cost_summary_by_service",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_cost_summary_by_account ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_cost_summary_by_account",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_cost_summary_by_region ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_cost_summary_by_region",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_compute_summary ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_compute_summary",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_compute_summary_by_service ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_compute_summary_by_service",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_compute_summary_by_account ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_compute_summary_by_account",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_compute_summary_by_region ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_compute_summary_by_region",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_storage_summary ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_storage_summary",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_storage_summary_by_service ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_storage_summary_by_service",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_storage_summary_by_account ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_storage_summary_by_account",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_storage_summary_by_region ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_storage_summary_by_region",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_network_summary ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_network_summary",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
            "ALTER TABLE reporting_aws_database_summary ADD COLUMN savingsplan_effective_cost",
            migrations.AddField(
                model_name="reporting_aws_database_summary",
                name="savingsplan_effective_cost",
                field=models.DecimalField(decimal_places=9, max_digits=24, null=True),
            ),
        )
    ]
