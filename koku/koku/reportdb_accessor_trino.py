#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Trino database accessor implementation."""
import logging

from django.conf import settings
import trino.dbapi
from koku.reportdb_accessor import ColumnType, ReportDBAccessor

LOG = logging.getLogger(__name__)


class TrinoReportDBAccessor(ReportDBAccessor):
    """Trino implementation of report database accessor."""

    def connect(self, **kwargs):
        """
        Create Trino database connection.

        Args:
            **kwargs: Connection parameters (host, port, catalog, schema, etc.)

        Returns:
            Trino DB-API 2.0 compatible connection object
        """
        return trino.dbapi.connect(**kwargs)

    def get_schema_check_sql(self, schema_name: str):
        return f"SHOW SCHEMAS LIKE '{schema_name}'"

    def get_table_check_sql(self, table_name: str, schema_name: str):
        return f"SHOW TABLES LIKE '{table_name}'"

    def get_schema_create_sql(self, schema_name: str):
        return f"CREATE SCHEMA IF NOT EXISTS {schema_name}"

    def get_table_create_sql(self, table_name: str, schema_name: str, columns: list[tuple[str, ColumnType]], partition_columns: list[tuple[str, ColumnType]], s3_path: str):
        sql = f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} ("

        for column in columns:
            sql += f"{column[0]} {self._get_column_type_sql(column[1])}, "
        for partition_column in partition_columns:
            sql += f"{partition_column[0]} {self._get_column_type_sql(partition_column[1])}, "
        sql = sql.rstrip(", ")
        
        partition_column_str = ", ".join([col_name for col_name, _ in partition_columns])

        sql += (
            f") WITH(external_location = '{settings.TRINO_S3A_OR_S3}://{s3_path}', format = 'PARQUET',"
            f" partitioned_by=ARRAY[{partition_column_str}])"
        )
        return sql

    def _get_column_type_sql(self, column_type: ColumnType):
        if column_type == ColumnType.NUMERIC:
            return "double"
        elif column_type == ColumnType.DATE:
            return "timestamp"
        elif column_type == ColumnType.BOOLEAN:
            return "boolean"
        else:
            return "varchar"

    def get_partition_create_sql(self, schema_name: str, table_name: str, partition_name: str, partition_values_lower: list[str], partition_values_upper: list[str]):
        """Trino doesn't need explicit partition creation - partitions are created automatically."""
        # Trino partitions are created automatically when data is inserted
        # This method is not used for Trino, but must exist to satisfy the abstract base class
        return ""

    def get_delete_day_by_manifestid_sql(self, schema_name: str, table_name: str, source: str, year: str, month: str, manifestid: str):
        """Trino delete by manifestid - not used, Trino uses S3 file deletion."""
        # Trino doesn't use SQL DELETE for parquet files
        # Instead it deletes S3 objects directly via _delete_old_data_trino()
        # This method exists only to satisfy the abstract base class
        return ""

    def get_delete_day_by_reportnumhours_sql(self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str, reportnumhours: int, date_column: str):
        """Trino delete by reportnumhours - not used, Trino uses S3 file deletion."""
        # Trino doesn't use SQL DELETE for parquet files
        # Instead it deletes S3 objects directly via _delete_old_data_trino()
        # This method exists only to satisfy the abstract base class
        return ""

    def get_check_day_exists_sql(self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str, date_column: str):
        """Trino check day exists - not used for Trino."""
        # Trino doesn't need this check - it uses S3 metadata
        # This method exists only to satisfy the abstract base class
        return ""

    def get_delete_by_month_sql(self, schema_name: str, table_name: str, source_column: str, source: str, year: str, month: str):
        """Generate Trino DELETE SQL for partitions by month."""
        return f"""DELETE FROM hive.{schema_name}.{table_name}
WHERE {source_column} = '{source}'
AND year = '{year}'
AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')"""

    def get_delete_by_day_sql(self, schema_name: str, table_name: str, source_column: str, source: str, year: str, month: str, day: str):
        """Generate Trino DELETE SQL for partitions by day."""
        return f"""DELETE FROM hive.{schema_name}.{table_name}
WHERE {source_column} = '{source}'
AND year = '{year}'
AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
AND day = '{day}'"""

    def get_delete_by_source_sql(self, schema_name: str, table_name: str, partition_column: str, provider_uuid: str):
        """Generate Trino DELETE SQL for partitions by source."""
        return f"""DELETE FROM hive.{schema_name}.{table_name}
WHERE {partition_column} = '{provider_uuid}'"""

    def get_expired_data_ocp_sql(self, schema_name: str, table_name: str, source_column: str, expired_date: str):
        """Generate Trino SQL to find expired partitions."""
        return f"""
SELECT partitions.year, partitions.month, partitions.source
FROM (
    SELECT year as year,
        month as month,
        day as day,
        cast(date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as date) as partition_date,
        {source_column} as source
    FROM  "{table_name}$partitions"
) as partitions
WHERE partitions.partition_date < DATE '{expired_date}'
GROUP BY partitions.year, partitions.month, partitions.source
"""

    def get_check_source_in_partitions_sql(self, schema_name: str, table_name: str, source_uuid: str):
        """Generate Trino SQL to check if source exists in table partitions."""
        return f"""
SELECT count(*) from hive.{schema_name}."{table_name}$partitions"
WHERE source = '{source_uuid}'
"""

    def get_nodes_query_sql(self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str):
        """Generate Trino SQL to get nodes from OpenShift cluster."""
        return f"""
SELECT ocp.node,
    ocp.resource_id,
    max(ocp.node_capacity_cpu_cores) as node_capacity_cpu_cores,
    coalesce(max(ocp.node_role), CASE
        WHEN contains(array_agg(DISTINCT ocp.namespace), 'openshift-kube-apiserver') THEN 'master'
        WHEN any_match(array_agg(DISTINCT nl.node_labels), element -> element like  '%"node_role_kubernetes_io": "infra"%') THEN 'infra'
        ELSE 'worker'
    END) as node_role,
    lower(json_extract_scalar(max(node_labels), '$.kubernetes_io_arch')) as arch
FROM hive.{schema_name}.openshift_pod_usage_line_items_daily as ocp
LEFT JOIN hive.{schema_name}.openshift_node_labels_line_items_daily as nl
    ON ocp.node = nl.node
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= TIMESTAMP '{start_date}'
    AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
    AND nl.source = '{source_uuid}'
    AND nl.year = '{year}'
    AND nl.month = '{month}'
    AND nl.interval_start >= TIMESTAMP '{start_date}'
    AND nl.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
GROUP BY ocp.node,
    ocp.resource_id
"""

    def get_pvcs_query_sql(self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str):
        """Generate Trino SQL to get PVCs from OpenShift cluster."""
        return f"""
SELECT distinct persistentvolume,
    persistentvolumeclaim,
    csi_volume_handle
FROM hive.{schema_name}.openshift_storage_usage_line_items_daily as ocp
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= TIMESTAMP '{start_date}'
    AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
"""

    def get_projects_query_sql(self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str):
        """Generate Trino SQL to get projects from OpenShift cluster."""
        return f"""
SELECT distinct namespace
FROM hive.{schema_name}.openshift_pod_usage_line_items_daily as ocp
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= TIMESTAMP '{start_date}'
    AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
"""

    def get_max_min_timestamp_sql(self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str):
        """Generate Trino SQL to get max/min timestamps from parquet data."""
        return f"""
SELECT min(interval_start) as min_timestamp,
    max(interval_start) as max_timestamp
FROM hive.{schema_name}.openshift_pod_usage_line_items_daily as ocp
WHERE ocp.source = '{source_uuid}'
    AND ocp.year = '{year}'
    AND ocp.month = '{month}'
    AND ocp.interval_start >= TIMESTAMP '{start_date}'
    AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
"""

    def get_delete_by_day_ocp_on_cloud_sql(self, schema_name: str, table_name: str, cloud_source: str, ocp_source: str, year: str, month: str, day: str):
        """Generate Trino DELETE SQL for OCP-on-cloud partitions by day."""
        return f"""DELETE FROM hive.{schema_name}.{table_name}
WHERE source = '{cloud_source}'
AND ocp_source = '{ocp_source}'
AND year = '{year}'
AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
AND day = '{day}'"""

    def get_bind_param_style(self):
        """Return the parameter binding style for Trino."""
        return "qmark"

    def get_gcp_topology_sql(self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str):
        """Generate Trino SQL to get GCP topology."""
        return f"""
SELECT source,
    billing_account_id,
    project_id,
    project_name,
    service_id,
    service_description,
    location_region
FROM hive.{schema_name}.gcp_line_items as gcp
WHERE gcp.source = '{source_uuid}'
    AND gcp.year = '{year}'
    AND gcp.month = '{month}'
    AND gcp.usage_start_time >= TIMESTAMP '{start_date}'
    AND gcp.usage_start_time < date_add('day', 1, TIMESTAMP '{end_date}')
GROUP BY source,
    billing_account_id,
    project_id,
    project_name,
    service_id,
    service_description,
    location_region
"""

    def get_data_validation_sql(self, schema_name: str, table_name: str, source_column: str, provider_filter: str, metric: str, date_column: str, start_date: str, end_date: str, year: str, month: str):
        """Generate Trino SQL for data validation query."""
        return f"""
SELECT sum({metric}) as metric, {date_column} as date
FROM hive.{schema_name}.{table_name}
    WHERE {source_column} = '{provider_filter}'
    AND {date_column} >= date('{start_date}')
    AND {date_column} <= date('{end_date}')
    AND year = '{year}'
    AND lpad(month, 2, '0') = '{month}'
    GROUP BY {date_column}
    ORDER BY {date_column}"""