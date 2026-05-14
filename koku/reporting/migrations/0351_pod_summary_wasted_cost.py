from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0350_widen_ratestousage_label_hash"),
    ]

    operations = [
        migrations.AddField(
            model_name="ocppodsummaryp",
            name="wasted_cpu_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.AddField(
            model_name="ocppodsummaryp",
            name="wasted_memory_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.AddField(
            model_name="ocppodsummarybyprojectp",
            name="wasted_cpu_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.AddField(
            model_name="ocppodsummarybyprojectp",
            name="wasted_memory_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.AddField(
            model_name="ocppodsummarybynodep",
            name="wasted_cpu_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
        migrations.AddField(
            model_name="ocppodsummarybynodep",
            name="wasted_memory_cost",
            field=models.DecimalField(decimal_places=15, max_digits=33, null=True),
        ),
    ]
