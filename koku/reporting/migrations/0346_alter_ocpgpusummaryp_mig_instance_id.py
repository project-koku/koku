from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0345_ocpgpusummaryp_gpu_uuid_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ocpgpusummaryp",
            name="mig_instance_id",
            field=models.CharField(max_length=128, null=True),
        ),
    ]
