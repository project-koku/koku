import pkgutil

from django.db import connection
from django.db import migrations


def add_views(apps, schema_editor):
    """Create database VIEWS from files."""
    view_sql = pkgutil.get_data(
        "reporting.provider.azure.openshift", f"sql/views/reporting_ocpazure_storage_summary.sql"
    )
    view_sql = view_sql.decode("utf-8")
    with connection.cursor() as cursor:
        cursor.execute(view_sql)

    view_sql = pkgutil.get_data(
        "reporting.provider.azure.openshift", f"sql/views/reporting_ocpazure_compute_summary.sql"
    )
    view_sql = view_sql.decode("utf-8")
    with connection.cursor() as cursor:
        cursor.execute(view_sql)


class Migration(migrations.Migration):

    dependencies = [("reporting", "0126_clear_org_units")]

    operations = [
        migrations.RunSQL(
            """
                WITH cte_split_units AS (
                    SELECT li.id,
                        li.currency,
                        CASE WHEN split_part(li.unit_of_measure, ' ', 2) != '' AND NOT (li.unit_of_measure = '100 Hours' AND li.service_name='Virtual Machines')
                            THEN  split_part(li.unit_of_measure, ' ', 1)::integer
                            ELSE 1::integer
                            END as multiplier,
                        CASE
                            WHEN split_part(li.unit_of_measure, ' ', 2) = 'Hours'
                                THEN  'Hrs'
                            WHEN split_part(li.unit_of_measure, ' ', 2) = 'GB/Month'
                                THEN  'GB-Mo'
                            WHEN split_part(li.unit_of_measure, ' ', 2) != ''
                                THEN  split_part(li.unit_of_measure, ' ', 2)
                            ELSE li.unit_of_measure
                        END as unit_of_measure
                        -- split_part(li.unit_of_measure, ' ', 2) as unit
                    FROM reporting_ocpazurecostlineitem_daily_summary AS li
                )
                UPDATE reporting_ocpazurecostlineitem_daily_summary AS li
                SET usage_quantity = li.usage_quantity * su.multiplier,
                    unit_of_measure = su.unit_of_measure
                FROM cte_split_units AS su
                WHERE li.id = su.id
                ;
                WITH cte_split_units AS (
                    SELECT li.id,
                        li.currency,
                        CASE WHEN split_part(li.unit_of_measure, ' ', 2) != '' AND NOT (li.unit_of_measure = '100 Hours' AND li.service_name='Virtual Machines')
                            THEN  split_part(li.unit_of_measure, ' ', 1)::integer
                            ELSE 1::integer
                            END as multiplier,
                        CASE
                            WHEN split_part(li.unit_of_measure, ' ', 2) = 'Hours'
                                THEN  'Hrs'
                            WHEN split_part(li.unit_of_measure, ' ', 2) = 'GB/Month'
                                THEN  'GB-Mo'
                            WHEN split_part(li.unit_of_measure, ' ', 2) != ''
                                THEN  split_part(li.unit_of_measure, ' ', 2)
                            ELSE li.unit_of_measure
                        END as unit_of_measure
                        -- split_part(li.unit_of_measure, ' ', 2) as unit
                    FROM reporting_ocpazurecostlineitem_project_daily_summary AS li
                )
                UPDATE reporting_ocpazurecostlineitem_project_daily_summary AS li
                SET usage_quantity = li.usage_quantity * su.multiplier,
                    unit_of_measure = su.unit_of_measure
                FROM cte_split_units AS su
                WHERE li.id = su.id
                ;
            """
        ),
        migrations.RunSQL(
            """
            DROP INDEX IF EXISTS ocpazure_compute_summary;
            DROP INDEX IF EXISTS ocpazure_storage_summary;
            DROP MATERIALIZED VIEW IF EXISTS reporting_ocpazure_compute_summary;
            DROP MATERIALIZED VIEW IF EXISTS reporting_ocpazure_storage_summary;
            """
        ),
        migrations.RunPython(add_views),
    ]
