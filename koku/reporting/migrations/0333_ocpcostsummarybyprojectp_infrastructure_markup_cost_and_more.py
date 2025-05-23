# Generated by Django 4.2.21 on 2025-05-09 08:46
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0332_remove_ocicomputesummarybyaccountp_source_uuid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ocpcostsummarybyprojectp",
            name="infrastructure_markup_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.AddField(
            model_name="ocpcostsummarybyprojectp",
            name="infrastructure_raw_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
    ]
