# Generated by Django 3.2.16 on 2023-03-06 19:52
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("cost_models", "0005_add_oci_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="costmodel",
            name="distribution_info",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="costmodelaudit",
            name="distribution_info",
            field=models.JSONField(default=dict),
        ),
        migrations.RunSQL(
            "UPDATE cost_model cm SET distribution_info = (SELECT to_jsonb(distribution_opts) FROM (select temp_cm.distribution as distribution_type, false as worker_cost, false as platform_cost from cost_model temp_cm where temp_cm.uuid = cm.uuid) distribution_opts)"
        ),
    ]
