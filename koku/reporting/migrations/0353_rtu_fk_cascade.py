# Change rates_to_usage FK on_delete from SET_NULL to CASCADE (GAP-2, team policy).
# Django ORM metadata only; PG constraint remains NO ACTION DEFERRABLE.
import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0352_rtu_truncate_and_fk_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ratestousage",
            name="rate",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="cost_models.rate",
            ),
        ),
        migrations.AlterField(
            model_name="ratestousage",
            name="cost_model",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="cost_models.costmodel",
            ),
        ),
    ]
