import uuid

from django.db import migrations
from django.db import models


def create_uuid(apps, schema_editor):
    awsenabledcategorykeys = apps.get_model("reporting", "awsenabledcategorykeys")
    for category in awsenabledcategorykeys.objects.all():
        category.uuid = uuid.uuid4()
        category.save()


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0289_alter_awsorganizationalunit_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="awsenabledcategorykeys",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(create_uuid, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name="awsenabledcategorykeys",
            name="key",
            field=models.CharField(max_length=253, unique=True),
        ),
        migrations.AlterField(
            model_name="awsenabledcategorykeys",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True),
        ),
    ]
