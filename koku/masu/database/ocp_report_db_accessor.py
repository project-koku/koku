#
# Copyright 2018 Red Hat, Inc.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Database accessor for OCP report data."""
import logging
import pkgutil
import uuid

from dateutil.parser import parse
from django.db import connection
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP, OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.provider.ocp.models import (OCPStorageLineItemDailySummary,
                                           OCPUsageLineItemDailySummary,
                                           OCPUsageReport,
                                           OCPUsageReportPeriod)

LOG = logging.getLogger(__name__)


# pylint: disable=too-many-public-methods
class OCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, column_map):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            column_map (dict): A mapping of report columns to database columns

        """
        super().__init__(schema, column_map)
        self._datetime_format = Config.OCP_DATETIME_STR_FORMAT
        self.column_map = column_map

    # pylint: disable=too-many-arguments,arguments-differ
    def merge_temp_table(self, table_name, temp_table_name, columns,
                         conflict_columns):
        """INSERT temp table rows into the primary table specified.

        Args:
            table_name (str): The main table to insert into
            temp_table_name (str): The temp table to pull from
            columns (list): A list of columns to use in the insert logic

        Returns:
            (None)

        """
        column_str = ','.join(columns)
        conflict_col_str = ','.join(conflict_columns)

        set_clause = ','.join([f'{column} = excluded.{column}'
                               for column in columns])
        upsert_sql = f"""
            INSERT INTO {table_name} ({column_str})
                SELECT {column_str}
                FROM {temp_table_name}
                ON CONFLICT ({conflict_col_str}) DO UPDATE
                SET {set_clause}
            """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(upsert_sql)

            delete_sql = f'DELETE FROM {temp_table_name}'
            cursor.execute(delete_sql)

    def get_current_usage_report(self):
        """Get the most recent usage report object."""
        table_name = OCP_REPORT_TABLE_MAP['report']

        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .order_by('-interval_start')\
                .first()

    def get_current_usage_period(self):
        """Get the most recent usage report period object."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .order_by('-report_period_start')\
                .first()

    def get_usage_periods_by_date(self, start_date):
        """Return all report period entries for the specified start date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(report_period_start=start_date)\
                .all()

    def get_usage_period_before_date(self, date):
        """Get the usage report period objects before provided date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            usage_period_query = base_query.filter(report_period_start__lte=date)
            return usage_period_query

    # pylint: disable=invalid-name
    def get_usage_period_query_by_provider(self, provider_id):
        """Return all report periods for the specified provider."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(provider_id=provider_id)

    def report_periods_for_provider_id(self, provider_id, start_date=None):
        """Return all report periods for provider_id on date."""
        report_periods = self.get_usage_period_query_by_provider(provider_id)
        with schema_context(self.schema):
            if start_date:
                report_date = parse(start_date).replace(day=1)
                report_periods = report_periods.filter(
                    report_period_start=report_date
                ).all()

            return report_periods

    def get_lineitem_query_for_reportid(self, query_report_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_id=query_report_id)
            return line_item_query

    def get_daily_usage_query_for_clusterid(self, cluster_identifier):
        """Get the usage report daily item for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_usage_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_usage_query

    def get_summary_usage_query_for_clusterid(self, cluster_identifier):
        """Get the usage report summary for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_usage_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_usage_query

    def get_item_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_storage_item_query_report_period_id(self, report_period_id):
        """Get the storage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_daily_storage_item_query_cluster_id(self, cluster_identifier):
        """Get the daily storage report line item for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_item_query

    def get_storage_summary_query_cluster_id(self, cluster_identifier):
        """Get the storage report summary for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_item_query

    def get_ocp_aws_summary_query_for_cluster_id(self, cluster_identifier):
        """Get the OCP-on-AWS report summary item for a given cluster id query."""
        table_name = AWS_CUR_TABLE_MAP['ocp_on_aws_daily_summary']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_item_query

    def get_ocp_aws_project_summary_query_for_cluster_id(self, cluster_identifier):
        """Get the OCP-on-AWS report project summary item for a given cluster id query."""
        table_name = AWS_CUR_TABLE_MAP['ocp_on_aws_project_daily_summary']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_item_query

    def get_report_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['report']
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            usage_report_query = base_query.filter(report_period_id=report_period_id)
            return usage_report_query

    def get_report_periods(self):
        """Get all usage period objects."""
        periods = []
        with schema_context(self.schema):
            periods = OCPUsageReportPeriod.objects.values('id', 'cluster_id',
                                                          'report_period_start', 'provider_id')
            return_value = {(p['cluster_id'], p['report_period_start'], p['provider_id']): p['id']
                            for p in periods}
            return return_value

    def get_reports(self):
        """Make a mapping of reports by time."""
        with schema_context(self.schema):
            reports = OCPUsageReport.objects.all()
            return {(entry.report_period_id,
                     entry.interval_start.strftime(self._datetime_format)): entry.id
                    for entry in reports}

    def get_pod_usage_cpu_core_hours(self, cluster_id=None):
        """Make a mapping of cpu pod usage hours."""
        table = OCPUsageLineItemDailySummary
        with schema_context(self.schema):
            if cluster_id:
                reports = self._get_db_obj_query(table).filter(cluster_id=cluster_id)
            else:
                reports = self._get_db_obj_query(table).all()
            return {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}

    def _get_reports(self, table, cluster_id=None):
        """Return requested reports from given table."""
        with schema_context(self.schema):
            if cluster_id:
                reports = self._get_db_obj_query(table).filter(cluster_id=cluster_id)
            else:
                reports = self._get_db_obj_query(table).all()
            return reports

    def get_pod_request_cpu_core_hours(self, cluster_id=None):
        """Make a mapping of cpu pod request hours."""
        table = OCPUsageLineItemDailySummary
        with schema_context(self.schema):
            reports = self._get_reports(table, cluster_id)
            return {entry.id: entry.pod_request_cpu_core_hours for entry in reports}

    def get_pod_usage_memory_gigabyte_hours(self, cluster_id=None):
        """Make a mapping of memory_usage hours."""
        table = OCPUsageLineItemDailySummary
        with schema_context(self.schema):
            reports = self._get_reports(table, cluster_id)
            return {entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports}

    def get_pod_request_memory_gigabyte_hours(self, cluster_id=None):
        """Make a mapping of memory_request_hours."""
        table = OCPUsageLineItemDailySummary
        with schema_context(self.schema):
            reports = self._get_reports(table, cluster_id)
            return {entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports}

    def get_persistentvolumeclaim_usage_gigabyte_months(self, cluster_id=None):
        """Make a mapping of persistentvolumeclaim_usage_gigabyte_months."""
        table = OCPStorageLineItemDailySummary
        with schema_context(self.schema):
            reports = self._get_reports(table, cluster_id)
            # pylint: disable=line-too-long
            return {entry.id: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}

    def get_volume_request_storage_gigabyte_months(self, cluster_id=None):
        """Make a mapping of volume_request_storage_gigabyte_months."""
        table = OCPStorageLineItemDailySummary
        with schema_context(self.schema):
            reports = self._get_reports(table, cluster_id)
            return {entry.id: entry.volume_request_storage_gigabyte_months for entry in reports}

    def populate_line_item_daily_table(self, start_date, end_date, cluster_id):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily']

        daily_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpusagelineitem_daily.sql'
        )
        daily_sql = daily_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date,
            cluster_id=cluster_id,
            schema=self.schema
        )
        self._commit_and_vacuum(table_name, daily_sql, start_date, end_date)

    def get_ocp_infrastructure_map(self, start_date, end_date):
        """Get the OCP on infrastructure map.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        infra_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpinfrastructure_provider_map.sql'
        )
        infra_sql = infra_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date,
            schema=self.schema
        )
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(infra_sql)
            results = cursor.fetchall()

        db_results = []
        for entry in results:
            db_dict = {}
            db_dict['aws_uuid'] = entry[0]
            db_dict['ocp_uuid'] = entry[1]
            db_dict['cluster_id'] = entry[2]
            db_results.append(db_dict)

        return db_results

    def populate_storage_line_item_daily_table(self, start_date, end_date, cluster_id):
        """Populate the daily storage aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily']

        daily_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpstoragelineitem_daily.sql'
        )
        daily_sql = daily_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date,
            cluster_id=cluster_id,
            schema=self.schema
        )
        self._commit_and_vacuum(table_name, daily_sql, start_date, end_date)

    def populate_pod_charge(self, cpu_temp_table, mem_temp_table):
        """Populate the memory and cpu charge on daily summary table.

        Args:
            cpu_temp_table (String) Name of cpu charge temp table
            mem_temp_table (String) Name of mem charge temp table

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        daily_charge_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpusagelineitem_daily_pod_charge.sql'
        )
        charge_line_sql = daily_charge_sql.decode('utf-8').format(
            cpu_temp=cpu_temp_table,
            mem_temp=mem_temp_table,
            schema=self.schema
        )

        self._commit_and_vacuum(table_name, charge_line_sql)

    def populate_storage_charge(self, temp_table_name):
        """Populate the storage charge into the daily summary table.

        Args:
            storage_charge (Float) Storage charge.

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']

        daily_charge_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocp_storage_charge.sql'
        )
        charge_line_sql = daily_charge_sql.decode('utf-8').format(
            temp_table=temp_table_name,
            schema=self.schema
        )
        self._commit_and_vacuum(table_name, charge_line_sql)

    def populate_line_item_daily_summary_table(self, start_date, end_date, cluster_id):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        summary_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpusagelineitem_daily_summary.sql'
        )
        summary_sql = summary_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date,
            end_date=end_date, cluster_id=cluster_id,
            schema=self.schema
        )
        self._commit_and_vacuum(table_name, summary_sql, start_date, end_date)

    def populate_storage_line_item_daily_summary_table(self, start_date, end_date, cluster_id):
        """Populate the daily aggregate of storage line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']

        summary_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpstoragelineitem_daily_summary.sql'
        )
        summary_sql = summary_sql.decode('utf-8').format(
            uuid=str(uuid.uuid4()).replace('-', '_'),
            start_date=start_date, end_date=end_date,
            cluster_id=cluster_id,
            schema=self.schema
        )
        self._commit_and_vacuum(table_name, summary_sql, start_date, end_date)

    def populate_cost_summary_table(self, cluster_id, start_date=None, end_date=None):
        """Populate the cost summary table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['cost_summary']
        if start_date is None:
            start_date_qry = self._get_db_obj_query(table_name).order_by('usage_start').first()
            start_date = str(start_date_qry.usage_start) if start_date_qry else None
        if end_date is None:
            end_date_qry = self._get_db_obj_query(table_name).order_by('-usage_start').first()
            end_date = str(end_date_qry.usage_start) if end_date_qry else None

        summary_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpcosts_summary.sql'
        )
        if start_date and end_date:
            summary_sql = summary_sql.decode('utf-8').format(
                uuid=str(uuid.uuid4()).replace('-', '_'),
                start_date=start_date,
                end_date=end_date,
                cluster_id=cluster_id,
                schema=self.schema
            )
            self._commit_and_vacuum(table_name, summary_sql, start_date, end_date)

    def get_cost_summary_for_clusterid(self, cluster_identifier):
        """Get the cost summary for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP['cost_summary']
        base_query = self._get_db_obj_query(table_name)
        cost_summary_query = base_query.filter(cluster_id=cluster_identifier)
        return cost_summary_query

    # pylint: disable=invalid-name
    def populate_pod_label_summary_table(self):
        """Populate the line item aggregated totals data table."""
        table_name = OCP_REPORT_TABLE_MAP['pod_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpusagepodlabel_summary.sql'
        )
        agg_sql = agg_sql.decode('utf-8').format(schema=self.schema)

        self._commit_and_vacuum(table_name, agg_sql)

    # pylint: disable=invalid-name
    def populate_volume_claim_label_summary_table(self):
        """Populate the OCP volume claim label summary table."""
        table_name = OCP_REPORT_TABLE_MAP['volume_claim_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpstoragevolumeclaimlabel_summary.sql'
        )
        agg_sql = agg_sql.decode('utf-8').format(schema=self.schema)

        self._commit_and_vacuum(table_name, agg_sql)

    # pylint: disable=invalid-name
    def populate_volume_label_summary_table(self):
        """Populate the OCP volume label summary table."""
        table_name = OCP_REPORT_TABLE_MAP['volume_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpstoragevolumelabel_summary.sql'
        )
        agg_sql = agg_sql.decode('utf-8').format(schema=self.schema)

        self._commit_and_vacuum(table_name, agg_sql)
