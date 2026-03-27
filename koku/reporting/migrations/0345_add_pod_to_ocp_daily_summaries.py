from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0344_add_mig_fields_to_gpu_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="ocpusagelineitemdailysummary",
            name="pod",
            field=models.CharField(max_length=253, null=True),
        ),
        migrations.AddField(
            model_name="ocpusagelineitemdailysummarystaging",
            name="pod",
            field=models.CharField(max_length=253, null=True),
        ),
    ]
