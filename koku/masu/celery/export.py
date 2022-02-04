"""Table export settings for masu celery tasks."""
import collections


TableExportSetting = collections.namedtuple("TableExportSetting", ["provider", "output_name", "iterate_daily", "sql"])
TableExportSetting.__doc__ = """\
Settings for exporting table data using a custom SQL query.

- provider (str): the provider service's name (e.g. "aws", "azure", "ocp")
- output_name (str): a name to use when saving the query's results
- iterate_daily (bool): if True, the query should be run once per day over a date range
- sql (str): raw SQL query to execute to gather table data
"""

table_export_settings = [
    TableExportSetting(
        "aws",
        "reporting_awscostentrylineitem",
        False,
        """
        SELECT *
        FROM
            {schema}.reporting_awscostentrylineitem li
            JOIN {schema}.reporting_awscostentrybill b ON li.cost_entry_bill_id = b.id
            JOIN {schema}.reporting_awscostentry e ON li.cost_entry_id = e.id
            LEFT JOIN {schema}.reporting_awscostentryproduct p ON li.cost_entry_product_id = p.id
            LEFT JOIN {schema}.reporting_awscostentryreservation r ON li.cost_entry_reservation_id = r.id
            LEFT JOIN {schema}.reporting_awscostentrypricing pr ON li.cost_entry_pricing_id = pr.id
        WHERE
            (
                e.interval_start BETWEEN %(start_date)s AND %(end_date)s
                OR e.interval_end BETWEEN %(start_date)s AND %(end_date)s
            )
            AND b.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "ocp",
        "reporting_ocpusagelineitem",
        False,
        """
        SELECT *
        FROM
            {schema}.reporting_ocpusagelineitem i
            JOIN {schema}.reporting_ocpusagereport r ON i.report_id = r.id
            JOIN {schema}.reporting_ocpusagereportperiod p ON i.report_period_id = p.id
        WHERE
            (
                r.interval_start BETWEEN %(start_date)s AND %(end_date)s
                OR r.interval_end BETWEEN %(start_date)s AND %(end_date)s
            )
            AND p.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "ocp",
        "reporting_ocpstoragelineitem",
        False,
        """
        SELECT *
        FROM
            {schema}.reporting_ocpstoragelineitem i
            JOIN {schema}.reporting_ocpusagereport r ON i.report_id = r.id
            JOIN {schema}.reporting_ocpusagereportperiod p ON i.report_period_id = p.id
        WHERE
            (
                r.interval_start BETWEEN %(start_date)s AND %(end_date)s
                OR r.interval_end BETWEEN %(start_date)s AND %(end_date)s
            )
            AND p.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "azure",
        "reporting_azurecostentrylineitem_daily",
        False,
        """
        SELECT d.*, s.*, m.*
        FROM
            {schema}.reporting_azurecostentrylineitem_daily d
            JOIN {schema}.reporting_azurecostentrybill b ON d.cost_entry_bill_id = b.id
            LEFT JOIN {schema}.reporting_azurecostentryproductservice s ON d.cost_entry_product_id = s.id
            LEFT JOIN {schema}.reporting_azuremeter m ON d.meter_id = m.id
        WHERE
            (
                b.billing_period_start BETWEEN %(start_date)s AND %(end_date)s
                OR b.billing_period_end BETWEEN %(start_date)s AND %(end_date)s
            )
            AND b.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "aws",
        "reporting_awscostentrylineitem_daily_summary",
        True,
        """
        SELECT ds.*, aa.account_id, aa.account_alias, b.*
        FROM
            {schema}.reporting_awscostentrylineitem_daily_summary ds
            JOIN {schema}.reporting_awscostentrybill b ON b.id = ds.cost_entry_bill_id
            LEFT JOIN {schema}.reporting_awsaccountalias aa ON aa.id = ds.account_alias_id
            -- LEFT JOIN because sometimes this doesn't exist, but it's unclear why.
            -- It seems that "real" data has it, but fake data from AWS-local+nise does not.
        WHERE
            ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
            AND b.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "azure",
        "reporting_azurecostentrylineitem_daily_summary",
        True,
        """
        SELECT ds.*, b.*, m.*
        FROM
            {schema}.reporting_azurecostentrylineitem_daily_summary ds
            JOIN {schema}.reporting_azurecostentrybill b ON b.id = ds.cost_entry_bill_id
            JOIN {schema}.reporting_azuremeter m ON m.id = ds.meter_id
        WHERE
            ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            AND b.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "ocp",
        "reporting_ocpawscostlineitem_daily_summary_p",
        True,
        """
        SELECT DISTINCT ds.*
        FROM
            {schema}.reporting_ocpawscostlineitem_daily_summary_p ds
            JOIN {schema}.reporting_ocpusagereportperiod rp ON ds.cluster_id = rp.cluster_id
        WHERE
            ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
            AND rp.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "ocp",
        "reporting_ocpawscostlineitem_project_daily_summary_p",
        True,
        """
        SELECT DISTINCT pds.*
        FROM
            {schema}.reporting_ocpawscostlineitem_project_daily_summary_p pds
            JOIN {schema}.reporting_ocpusagereportperiod rp ON pds.cluster_id = rp.cluster_id
        WHERE
            pds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
            AND rp.provider_id = %(provider_uuid)s
        """,
    ),
    TableExportSetting(
        "ocp",
        "reporting_ocpusagelineitem_daily_summary",
        True,
        """
        SELECT DISTINCT ds.*
        FROM
            {schema}.reporting_ocpusagelineitem_daily_summary ds
            JOIN {schema}.reporting_ocpusagereportperiod rp ON ds.cluster_id = rp.cluster_id
        WHERE
            ds.usage_start BETWEEN %(start_date)s AND %(end_date)s
            -- No need to filter usage_end because usage_end should always match usage_start for this table.
            AND rp.provider_id = %(provider_uuid)s
        """,
    ),
]
