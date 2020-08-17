from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("reporting", "0124_auto_20200806_1943")]

    operations = [
        migrations.RunSQL(
            """
DELETE FROM reporting_awsorganizationalunit;
            """
        )
    ]
