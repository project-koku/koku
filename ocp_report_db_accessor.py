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

from masu.config import Config
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase

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
        self._cursor.execute(upsert_sql)
        self._pg2_conn.commit()

        delete_sql = f'DELETE FROM {temp_table_name}'
        self._cursor.execute(delete_sql)
        self._pg2_conn.commit()
        self.vacuum_table(temp_table_name)

    def get_current_usage_report(self):
        """Get the most recent usage report object."""
        table_name = OCP_REPORT_TABLE_MAP['report']
        interval_start = getattr(
            getattr(self.report_schema, table_name),
            'interval_start'
        )

        return self._get_db_obj_query(table_name)\
            .order_by(interval_start.desc())\
            .first()

    def get_current_usage_period(self):
        """Get the most recent usage report period object."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_period_start = getattr(
            getattr(self.report_schema, table_name),
            'report_period_start'
        )

        return self._get_db_obj_query(table_name)\
            .order_by(report_period_start.desc())\
            .first()

    def get_usage_periods_by_date(self, start_date):
        """Return all report period entries for the specified start date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        return self._get_db_obj_query(table_name)\
            .filter_by(report_period_start=start_date)\
            .all()

    def get_usage_period_before_date(self, date):
        """Get the usage report period objects before provided date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        report_start = getattr(
            getattr(self.report_schema, table_name),
            'report_period_start'
        )
        base_query = self._get_db_obj_query(table_name)
        usage_period_query = base_query.filter(report_start <= date)
        return usage_period_query

    # pylint: disable=invalid-name
    def get_usage_period_query_by_provider(self, provider_id):
        """Return all report periods for the specified provider."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        return self._get_db_obj_query(table_name)\
            .filter_by(provider_id=provider_id)

    def get_lineitem_query_for_reportid(self, query_report_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        report_id = getattr(
            getattr(self.report_schema, table_name),
            'id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(query_report_id == report_id)
        return line_item_query

    def get_item_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['line_item']
        period_id = getattr(
            getattr(self.report_schema, table_name),
            'report_period_id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(report_period_id == period_id)
        return line_item_query

    def get_storage_item_query_report_period_id(self, report_period_id):
        """Get the storage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item']
        period_id = getattr(
            getattr(self.report_schema, table_name),
            'report_period_id'
        )
        base_query = self._get_db_obj_query(table_name)
        line_item_query = base_query.filter(report_period_id == period_id)
        return line_item_query

    def get_report_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP['report']
        period_id = getattr(
            getattr(self.report_schema, table_name),
            'report_period_id'
        )
        base_query = self._get_db_obj_query(table_name)
        usage_report_query = base_query.filter(report_period_id == period_id)
        return usage_report_query

    def get_report_periods(self):
        """Get all usage period objects."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        columns = ['id', 'cluster_id', 'report_period_start', 'provider_id']
        periods = self._get_db_obj_query(table_name, columns=columns).all()

        return {(p.cluster_id, p.report_period_start, p.provider_id): p.id
                for p in periods}

    def get_reports(self):
        """Make a mapping of reports by time."""
        table_name = OCP_REPORT_TABLE_MAP['report']

        reports = self._get_db_obj_query(table_name).all()

        return {(entry.report_period_id,
                 entry.interval_start.strftime(self._datetime_format)): entry.id
                for entry in reports}

    def get_pod_usage_cpu_core_hours(self, cluster_id=None):
        """Make a mapping of cpu pod usage hours."""
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        if cluster_id:
            reports = self._get_db_obj_query(table_name).filter_by(cluster_id=cluster_id)
        else:
            reports = self._get_db_obj_query(table_name).all()
        return {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}

    def _get_reports(self, table, cluster_id=None):
        """Return requested reports from given table."""
        if cluster_id:
            reports = self._get_db_obj_query(table).filter_by(cluster_id=cluster_id)
        else:
            reports = self._get_db_obj_query(table).all()
        return reports

    def get_pod_request_cpu_core_hours(self, cluster_id=None):
        """Make a mapping of cpu pod request hours."""
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        reports = self._get_reports(table_name, cluster_id)
        return {entry.id: entry.pod_request_cpu_core_hours for entry in reports}

    def get_pod_usage_memory_gigabyte_hours(self, cluster_id=None):
        """Make a mapping of memory_usage hours."""
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        reports = self._get_reports(table_name, cluster_id)
        return {entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports}

    def get_pod_request_memory_gigabyte_hours(self, cluster_id=None):
        """Make a mapping of memory_request_hours."""
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        reports = self._get_reports(table_name, cluster_id)
        return {entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports}

    def get_persistentvolumeclaim_usage_gigabyte_months(self, cluster_id=None):
        """Make a mapping of persistentvolumeclaim_usage_gigabyte_months."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']
        reports = self._get_reports(table_name, cluster_id)
        return {entry.id: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}

    def get_volume_request_storage_gigabyte_months(self, cluster_id=None):
        """Make a mapping of volume_request_storage_gigabyte_months."""
        table_name = OCP_REPORT_TABLE_MAP['storage_line_item_daily_summary']
        reports = self._get_reports(table_name, cluster_id)
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
            cluster_id=cluster_id
        )
        self._commit_and_vacuum(table_name, daily_sql, start_date, end_date)

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
            cluster_id=cluster_id
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
            mem_temp=mem_temp_table
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
            temp_table=temp_table_name
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
            end_date=end_date,
            cluster_id=cluster_id
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
            start_date=start_date,
            end_date=end_date,
            cluster_id=cluster_id
        )
        self._commit_and_vacuum(table_name, summary_sql, start_date, end_date)

    # pylint: disable=invalid-name
    def populate_pod_label_summary_table(self):
        """Populate the line item aggregated totals data table."""
        table_name = OCP_REPORT_TABLE_MAP['pod_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpusagepodlabel_summary.sql'
        )

        self._commit_and_vacuum(table_name, agg_sql)

    # pylint: disable=invalid-name
    def populate_volume_claim_label_summary_table(self):
        """Populate the OCP volume claim label summary table."""
        table_name = OCP_REPORT_TABLE_MAP['volume_claim_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpstoragevolumeclaimlabel_summary.sql'
        )

        self._commit_and_vacuum(table_name, agg_sql)

    # pylint: disable=invalid-name
    def populate_volume_label_summary_table(self):
        """Populate the OCP volume label summary table."""
        table_name = OCP_REPORT_TABLE_MAP['volume_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpstoragevolumelabel_summary.sql'
        )

        self._commit_and_vacuum(table_name, agg_sql)
