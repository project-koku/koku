from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0351_create_ocp_cost_breakdown_p"),
    ]

    operations = [
        # The contents of this migration file was moved to 0353
        # The design of the migration runs with the expectation
        # that no workers are actively inserting into the RTU table.
        # We missed an rouge insert and the fix with (943aaa4) which lands
        # afterthis migration was added to the git history. Due to automatic
        # stage releases the migration was ran Stage, but not in Prod.
        # Therefore, we changed this migration to no op and ported
        # the changes over to 0353 in order to ensure no inserts happen
        # on the RTU table as we run the migration.
    ]
