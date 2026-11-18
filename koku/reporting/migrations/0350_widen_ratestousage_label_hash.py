from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("reporting", "0349_ratestousage_composite_index")]

    operations = [
        migrations.AlterField(
            model_name="ratestousage",
            name="label_hash",
            field=models.CharField(max_length=64, null=True),
        ),
    ]
