#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""PostgreSQL database accessor implementation."""
import logging

from koku.reportdb_accessor import ReportDBAccessor

LOG = logging.getLogger(__name__)

# Date column used for partitioning in self-hosted line item tables
DATE_COLUMN = "usage_start"


class DjangoConnectionWrapper:
    """Wrapper to make Django connection work like a DB-API connection with context manager."""

    def __init__(self, schema=None):
        from django.db import connection

        # Set schema if provided
        if schema and schema != "default":
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [schema])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Django manages connection lifecycle, we don't close it
        return False

    def cursor(self):
        from django.db import connection

        return connection.cursor()

    def getConnection(self):
        """Return the underlying Django connection for compatibility."""
        from django.db import connection

        return connection.connection


class PostgresReportDBAccessor(ReportDBAccessor):
    """PostgreSQL implementation of report database accessor using Django DB API."""

    def connect(self, **kwargs):
        """
        Create PostgreSQL database connection.

        Args:
            **kwargs: Connection parameters (ignored for Django)

        Returns:
            DB-API 2.0 compatible connection object
        """
        schema = kwargs.get("schema")
        return DjangoConnectionWrapper(schema=schema)

    def get_schema_check_sql(self, schema_name: str):
        """Return the SQL to check if a schema exists."""
        return f"SELECT 1 FROM information_schema.schemata WHERE schema_name = '{schema_name}'"

    def get_table_check_sql(self, table_name: str, schema_name: str):
        return (
            f"SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{table_name}' AND table_schema = '{schema_name}'"
        )

    def get_delete_day_by_manifestid_sql(
        self, schema_name: str, table_name: str, source: str, year: str, month: str, manifestid: str
    ):
        """Return the SQL to delete data where manifestid doesn't match."""
        return f"""
            DELETE FROM "{schema_name}"."{table_name}"
            WHERE source = '{source}'
              AND year = '{year}'
              AND month = '{month}'
              AND manifestid != '{manifestid}'
        """

    def get_delete_day_by_reportnumhours_sql(
        self,
        schema_name: str,
        table_name: str,
        source: str,
        year: str,
        month: str,
        start_date: str,
        reportnumhours: int,
    ):
        """Return the SQL to delete a day's data where reportnumhours is less than specified value."""
        return f"""
            DELETE FROM "{schema_name}"."{table_name}"
            WHERE source = '{source}'
              AND year = '{year}'
              AND month = '{month}'
              AND {DATE_COLUMN} = DATE '{start_date}'
              AND reportnumhours < {reportnumhours}
        """

    def get_check_day_exists_sql(
        self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str
    ):
        """Return the SQL to check if data exists for a specific day."""
        return f"""
            SELECT 1
            FROM "{schema_name}"."{table_name}"
            WHERE source = '{source}'
              AND year = '{year}'
              AND month = '{month}'
              AND {DATE_COLUMN} = DATE '{start_date}'
            LIMIT 1
        """

    def get_delete_by_month_sql(
        self, schema_name: str, table_name: str, source_column: str, source: str, year: str, month: str
    ):
        """Generate PostgreSQL DELETE SQL for partitions by month."""
        return f"""DELETE FROM "{schema_name}".{table_name}
WHERE {source_column} = '{source}'
AND year = '{year}'
AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')"""

    def get_delete_by_day_sql(
        self, schema_name: str, table_name: str, source_column: str, source: str, year: str, month: str, day: str
    ):
        """Generate PostgreSQL DELETE SQL for partitions by day."""
        return f"""DELETE FROM "{schema_name}".{table_name}
WHERE {source_column} = '{source}'
AND year = '{year}'
AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
AND day = '{day}'"""

    def get_delete_by_source_sql(self, schema_name: str, table_name: str, partition_column: str, provider_uuid: str):
        """Generate PostgreSQL DELETE SQL for partitions by source."""
        return f"""DELETE FROM "{schema_name}".{table_name}
WHERE {partition_column} = '{provider_uuid}'"""

    def get_expired_data_ocp_sql(self, schema_name: str, table_name: str, source_column: str, expired_date: str):
        """Generate PostgreSQL SQL to find expired data."""
        return f"""
SELECT DISTINCT year, month, {source_column}
FROM "{schema_name}".{table_name}
WHERE usage_start < DATE '{expired_date}'
"""

    def get_check_source_in_partitions_sql(self, schema_name: str, table_name: str, source_uuid: str):
        """Generate PostgreSQL SQL to check if source exists in table."""
        return f"""
SELECT count(*) FROM "{schema_name}".{table_name}
WHERE source = '{source_uuid}'
"""

    def get_nodes_query_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Generate PostgreSQL SQL to get nodes from OpenShift cluster."""
        return f"""
SELECT ocp.node,
    ocp.resource_id,
    max(ocp.node_capacity_cpu_cores) as node_capacity_cpu_cores,
    coalesce(max(ocp.node_role), CASE
        WHEN 'openshift-kube-apiserver' = ANY(array_agg(DISTINCT ocp.namespace)) THEN 'master'
        WHEN EXISTS (
            SELECT 1 FROM unnest(array_agg(DISTINCT nl.node_labels)) AS label
            WHERE label::text LIKE '%%"node_role_kubernetes_io": "infra"%%'
        ) THEN 'infra'
        ELSE 'worker'
    END) as node_role,
    lower(max(node_labels)::json->>'kubernetes_io_arch') as arch
FROM "{schema_name}".openshift_pod_usage_line_items_daily as ocp
LEFT JOIN "{schema_name}".openshift_node_labels_line_items_daily as nl
    ON ocp.node = nl.node
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= '{start_date}'::timestamp
    AND ocp.interval_start < '{end_date}'::timestamp + INTERVAL '1 day'
    AND nl.source = '{source_uuid}'
    AND nl.year = '{year}'
    AND nl.month = '{month}'
    AND nl.interval_start >= '{start_date}'::timestamp
    AND nl.interval_start < '{end_date}'::timestamp + INTERVAL '1 day'
GROUP BY ocp.node,
    ocp.resource_id
"""

    def get_pvcs_query_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Generate PostgreSQL SQL to get PVCs from OpenShift cluster."""
        return f"""
SELECT distinct persistentvolume,
    persistentvolumeclaim,
    csi_volume_handle
FROM "{schema_name}".openshift_storage_usage_line_items_daily as ocp
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= '{start_date}'::timestamp
    AND ocp.interval_start < '{end_date}'::timestamp + INTERVAL '1 day'
"""

    def get_projects_query_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Generate PostgreSQL SQL to get projects from OpenShift cluster."""
        return f"""
SELECT distinct namespace
FROM "{schema_name}".openshift_pod_usage_line_items_daily as ocp
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= '{start_date}'::timestamp
    AND ocp.interval_start < '{end_date}'::timestamp + INTERVAL '1 day'
"""

    def get_max_min_timestamp_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Generate PostgreSQL SQL to get max/min timestamps from parquet data."""
        return f"""
SELECT min(interval_start) as min_timestamp,
    max(interval_start) as max_timestamp
FROM "{schema_name}".openshift_pod_usage_line_items_daily as ocp
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= '{start_date}'::timestamp
    AND ocp.interval_start < '{end_date}'::timestamp + INTERVAL '1 day'
"""

    def get_delete_by_day_ocp_on_cloud_sql(
        self, schema_name: str, table_name: str, cloud_source: str, ocp_source: str, year: str, month: str, day: str
    ):
        """Generate PostgreSQL DELETE SQL for OCP-on-cloud partitions by day."""
        return f"""DELETE FROM "{schema_name}".{table_name}
WHERE source = '{cloud_source}'
AND ocp_source = '{ocp_source}'
AND year = '{year}'
AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
AND day = '{day}'"""

    def get_bind_param_style(self):
        """Return the parameter binding style for PostgreSQL."""
        return "pyformat"

    def get_gcp_topology_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Generate PostgreSQL SQL to get GCP topology."""
        return f"""
SELECT source,
    billing_account_id,
    project_id,
    project_name,
    service_id,
    service_description,
    location_region
FROM "{schema_name}".gcp_line_items as gcp
WHERE gcp.source = '{source_uuid}'
    AND gcp.year = '{year}'
    AND gcp.month = '{month}'
    AND gcp.usage_start_time >= '{start_date}'::timestamp
    AND gcp.usage_start_time < '{end_date}'::timestamp + INTERVAL '1 day'
GROUP BY source,
    billing_account_id,
    project_id,
    project_name,
    service_id,
    service_description,
    location_region
"""

    def get_data_validation_sql(
        self,
        schema_name: str,
        table_name: str,
        source_column: str,
        provider_filter: str,
        metric: str,
        date_column: str,
        start_date: str,
        end_date: str,
        year: str,
        month: str,
    ):
        """Generate PostgreSQL SQL for data validation query."""
        return f"""
SELECT sum({metric}) as metric, {date_column} as date
FROM {schema_name}.{table_name}_{year}_{month}
    WHERE {source_column} = '{provider_filter}'
    AND {date_column} >= '{start_date}'
    AND {date_column} <= '{end_date}'
    GROUP BY {date_column}
    ORDER BY {date_column}"""
