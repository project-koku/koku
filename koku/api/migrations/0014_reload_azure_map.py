import json
import pkgutil

import django.contrib.postgres.fields.jsonb
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations
from django.db import models


def reload_azure_map(apps, schema_editor):
    """Update report to database mapping."""
    ReportColumnMap = apps.get_model("reporting_common", "ReportColumnMap")
    azure_items = ReportColumnMap.objects.filter(provider_type="AZURE")
    azure_items.delete()

    data = pkgutil.get_data("reporting_common", "data/azure_report_column_map.json")

    data = json.loads(data)

    for entry in data:
        map = ReportColumnMap(**entry)
        map.save()


class Migration(migrations.Migration):

    dependencies = [("api", "0013_auto_20200226_1953")]

    operations = [migrations.RunPython(code=reload_azure_map)]
