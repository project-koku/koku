import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations
from django.db import models
from django.db import transaction


def update_platform_category(apps, schema_editor):
    OpenshiftCostCategory = apps.get_model("reporting", "OpenshiftCostCategory")
    model_qs = OpenshiftCostCategory.objects.filter(name="platform")
    # name is a unique key constraint so there can only be one.
    for model_obj in model_qs:
        model_obj.name = "Platform"
        model_obj.namespace = ["openshift-%", "kube-%", "Platform unallocated"]
        model_obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0266_ocpgcp_precision"),
    ]

    operations = [
        migrations.RunPython(update_platform_category),
    ]
