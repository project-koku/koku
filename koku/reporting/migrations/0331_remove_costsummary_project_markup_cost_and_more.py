# Generated by Django 4.2.20 on 2025-04-21 14:17
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0330_alter_ocpusagelineitemdailysummary_monthly_cost_type"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="costsummary",
            name="project_markup_cost",
        ),
        migrations.RemoveField(
            model_name="ocpallcostlineitemprojectdailysummaryp",
            name="pod_cost",
        ),
        migrations.RemoveField(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            name="pod_cost",
        ),
        migrations.RemoveField(
            model_name="ocpawscostlineitemprojectdailysummaryp",
            name="project_markup_cost",
        ),
        migrations.RemoveField(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            name="pod_cost",
        ),
        migrations.RemoveField(
            model_name="ocpazurecostlineitemprojectdailysummaryp",
            name="project_markup_cost",
        ),
        migrations.RemoveField(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            name="pod_cost",
        ),
        migrations.RemoveField(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            name="pod_credit",
        ),
        migrations.RemoveField(
            model_name="ocpgcpcostlineitemprojectdailysummaryp",
            name="project_markup_cost",
        ),
    ]
