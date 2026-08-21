# Widen OCPCostUIBreakDownP.path/parent_path from CharField(512) to TextField.
#
# path/parent_path concatenate up to 2 k8s names (namespace + node, each up to
# 253 chars) plus a custom_name (50 chars) and fixed segment prefixes. Worst
# case (depth 5, namespace + node both present) is ~598 chars, which already
# exceeds the previous 512 limit and would risk StringDataRightTruncation on
# insert. See docs/agent/ga-readiness-review-patterns.md pattern 6.
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0354_rtu_capacity_columns_and_distribution_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ocpcostuibreakdownp",
            name="parent_path",
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name="ocpcostuibreakdownp",
            name="path",
            field=models.TextField(),
        ),
    ]
