from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [("reporting_common", "0031_costusagereportmanifest_export_time")]

    operations = [
        migrations.AddField(
            model_name="costusagereportmanifest", name="last_reports", field=models.JSONField(default=dict, null=True)
        )
    ]
