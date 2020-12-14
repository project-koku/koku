import pkgutil

from django.db import connection
from django.db import migrations


def add_gcp_views(apps, schema_editor):
    """Create the GCP Materialized views from files."""

    for view in ("", "_by_account", "_by_service", "_by_region", "_by_project"):
        view_sql = pkgutil.get_data("reporting.provider.gcp", f"sql/views/reporting_gcp_cost_summary{view}.sql")
        view_sql = view_sql.decode("utf-8")
        with connection.cursor() as cursor:
            cursor.execute(view_sql)


class Migration(migrations.Migration):

    dependencies = [("reporting", "0156_auto_20201208_2029")]

    operations = [migrations.RunPython(add_gcp_views)]
