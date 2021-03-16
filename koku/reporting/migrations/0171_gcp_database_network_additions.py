import pkgutil

from django.db import connection
from django.db import migrations


def add_gcp_views(apps, schema_editor):
    """Create the GCP Materialized views from files."""
    views = ("sql/views/reporting_gcp_network_summary.sql", "sql/views/reporting_gcp_database_summary.sql")
    for view in views:
        view_sql = pkgutil.get_data("reporting.provider.gcp", view)
        view_sql = view_sql.decode("utf-8")
        with connection.cursor() as cursor:
            cursor.execute(view_sql)


class Migration(migrations.Migration):

    dependencies = [("reporting", "0170_auto_20210305_1659")]

    operations = [migrations.RunPython(add_gcp_views)]
