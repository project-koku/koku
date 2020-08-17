from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("reporting", "0125_azure_unit_normalization")]

    operations = [
        migrations.RunSQL(
            """
UPDATE reporting_awscostentrylineitem_daily_summary set organizational_unit_id = NULL
            """
        ),
        migrations.RunSQL(
            """
DELETE FROM reporting_awsorganizationalunit;
            """
        ),
    ]
