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
import datetime
import logging
import pkgutil
import uuid
from typing import Optional

from dateutil.rrule import MONTHLY, rrule
from django.db import connection
from django.db.models import DecimalField, F, Max, Min, Value
from django.db.models.functions import Coalesce
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP, OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.common import month_date_range_tuple
from reporting.provider.ocp.models import (OCPUsageLineItemDailySummary,
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
        self.jinja_sql = JinjaSql()

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

    def get_usage_period_by_dates_and_cluster(self, start_date, end_date, cluster_id):
        """Return all report period entries for the specified start date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(report_period_start=start_date,
                        report_period_end=end_date,
                        cluster_id=cluster_id)\
                .first()

    def get_usage_period_before_date(self, date):
        """Get the usage report period objects before provided date."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']

        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            usage_period_query = base_query.filter(report_period_start__lte=date)
            return usage_period_query

    # pylint: disable=invalid-name
    def get_usage_period_query_by_provider(self, provider_uuid):
        """Return all report periods for the specified provider."""
        table_name = OCP_REPORT_TABLE_MAP['report_period']
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name)\
                .filter(provider_id=provider_uuid)

    def report_periods_for_provider_uuid(self, provider_uuid, start_date: Optional[datetime.datetime] = None): # noqa E501
        """Return all report periods for provider_uuid on date."""
        report_periods = self.get_usage_period_query_by_provider(provider_uuid)
        with schema_context(self.schema):
            if start_date:
                report_date = start_date.replace(day=1)
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
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
        filters = {
            'cluster_id': cluster_identifier,
            'data_source': 'Storage'
        }
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(**filters)
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

    def get_pod_usage_cpu_core_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of cpu pod usage hours."""
        table = OCPUsageLineItemDailySummary
        filters = {
            'data_source': 'Pod',
            'usage_start__gte': start_date,
            'usage_start__lte': end_date
        }
        if cluster_id:
            filters['cluster_id'] = cluster_id
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.id: entry.pod_usage_cpu_core_hours for entry in reports}

    def _get_reports(self, table, filters=None):
        """Return requested reports from given table.

        Args:
            table (Django models.Model object): The table to query against
            filters (dict): Columns to filter the query on

        Returns:
            (QuerySet): Django queryset of objects queried on

        """
        with schema_context(self.schema):
            if filters:
                reports = self._get_db_obj_query(table).filter(**filters).all()
            else:
                reports = self._get_db_obj_query(table).all()
            return reports

    def get_pod_request_cpu_core_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of cpu pod request hours."""
        table = OCPUsageLineItemDailySummary
        filters = {
            'data_source': 'Pod',
            'usage_start__gte': start_date,
            'usage_start__lte': end_date
        }
        if cluster_id:
            filters['cluster_id'] = cluster_id
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.id: entry.pod_request_cpu_core_hours for entry in reports}

    def get_pod_usage_memory_gigabyte_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of memory_usage hours."""
        table = OCPUsageLineItemDailySummary
        filters = {
            'data_source': 'Pod',
            'usage_start__gte': start_date,
            'usage_start__lte': end_date
        }
        if cluster_id:
            filters['cluster_id'] = cluster_id
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.id: entry.pod_usage_memory_gigabyte_hours for entry in reports}

    def get_pod_request_memory_gigabyte_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of memory_request_hours."""
        table = OCPUsageLineItemDailySummary
        filters = {
            'data_source': 'Pod',
            'usage_start__gte': start_date,
            'usage_start__lte': end_date
        }
        if cluster_id:
            filters['cluster_id'] = cluster_id
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.id: entry.pod_request_memory_gigabyte_hours for entry in reports}

    def get_persistentvolumeclaim_usage_gigabyte_months(self, start_date,
                                                        end_date, cluster_id=None):
        """Make a mapping of persistentvolumeclaim_usage_gigabyte_months."""
        table = OCPUsageLineItemDailySummary
        filters = {
            'data_source': 'Storage',
            'usage_start__gte': start_date,
            'usage_start__lte': end_date
        }
        if cluster_id:
            filters['cluster_id'] = cluster_id
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            # pylint: disable=line-too-long
            return {entry.id: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}

    def get_volume_request_storage_gigabyte_months(self, start_date, end_date, cluster_id=None):
        """Make a mapping of volume_request_storage_gigabyte_months."""
        table = OCPUsageLineItemDailySummary
        filters = {
            'data_source': 'Storage',
            'usage_start__gte': start_date,
            'usage_start__lte': end_date
        }
        if cluster_id:
            filters['cluster_id'] = cluster_id
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.id: entry.volume_request_storage_gigabyte_months for entry in reports}

    def populate_line_item_daily_table(self, start_date: datetime.date, end_date: datetime.date, cluster_id) -> None:  # noqa: E501 pylint: disable=line-too-long
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
        daily_sql = daily_sql.decode('utf-8')
        daily_sql_params = {
            'uuid': str(uuid.uuid4()).replace('-', '_'),
            'start_date': start_date,
            'end_date': end_date,
            'cluster_id': cluster_id,
            'schema': self.schema
        }
        daily_sql, daily_sql_params = self.jinja_sql.prepare_query(
            daily_sql, daily_sql_params
        )
        self._execute_raw_sql_query(
            table_name, daily_sql, start_date, end_date, bind_params=list(daily_sql_params))

    def get_ocp_infrastructure_map(self, start_date: datetime.date, end_date: datetime.date, **kwargs) -> None:  # noqa: E501 pylint: disable=line-too-long
        """Get the OCP on infrastructure map.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        # kwargs here allows us to optionally pass in a provider UUID based on
        # the provider type this is run for
        ocp_provider_uuid = kwargs.get('ocp_provider_uuid')
        aws_provider_uuid = kwargs.get('aws_provider_uuid')
        azure_provider_uuid = kwargs.get('azure_provider_uuid')

        infra_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocpinfrastructure_provider_map.sql'
        )
        infra_sql = infra_sql.decode('utf-8')
        infra_sql_params = {
            'uuid': str(uuid.uuid4()).replace('-', '_'),
            'start_date': start_date,
            'end_date': end_date,
            'schema': self.schema,
            'aws_provider_uuid': aws_provider_uuid,
            'ocp_provider_uuid': ocp_provider_uuid,
            'azure_provider_uuid': azure_provider_uuid
        }
        infra_sql, infra_sql_params = self.jinja_sql.prepare_query(
            infra_sql, infra_sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(infra_sql, list(infra_sql_params))
            results = cursor.fetchall()

        db_results = {}
        for entry in results:
            # This dictionary is keyed on an OpenShift provider UUID
            # and the tuple contains
            # (Infrastructure Provider UUID, Infrastructure Provider Type)
            db_results[entry[0]] = (entry[1], entry[2])

        return db_results

    def populate_storage_line_item_daily_table(self, start_date: datetime.date,
                                               end_date: datetime.date, cluster_id) -> None:
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
        daily_sql = daily_sql.decode('utf-8')
        daily_sql_params = {
            'uuid': str(uuid.uuid4()).replace('-', '_'),
            'start_date': start_date,
            'end_date': end_date,
            'cluster_id': cluster_id,
            'schema': self.schema
        }
        daily_sql, daily_sql_params = self.jinja_sql.prepare_query(
            daily_sql, daily_sql_params
        )
        self._execute_raw_sql_query(
            table_name, daily_sql, start_date, end_date, bind_params=list(daily_sql_params))

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
        charge_line_sql = daily_charge_sql.decode('utf-8')
        charge_line_sql_params = {
            'cpu_temp': cpu_temp_table,
            'mem_temp': mem_temp_table,
            'schema': self.schema
        }
        charge_line_sql, charge_line_sql_params = self.jinja_sql.prepare_query(
            charge_line_sql, charge_line_sql_params
        )
        self._execute_raw_sql_query(
            table_name, charge_line_sql, bind_params=list(charge_line_sql_params))

    def populate_storage_charge(self, temp_table_name):
        """Populate the storage charge into the daily summary table.

        Args:
            storage_charge (Float) Storage charge.

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']

        daily_charge_sql = pkgutil.get_data(
            'masu.database',
            'sql/reporting_ocp_storage_charge.sql'
        )
        charge_line_sql = daily_charge_sql.decode('utf-8')
        charge_line_sql_params = {
            'temp_table': temp_table_name,
            'schema': self.schema
        }
        charge_line_sql, charge_line_sql_params = self.jinja_sql.prepare_query(
            charge_line_sql, charge_line_sql_params
        )
        self._execute_raw_sql_query(
            table_name, charge_line_sql, bind_params=list(charge_line_sql_params))

    def populate_line_item_daily_summary_table(self, start_date: datetime.date,
                                               end_date: datetime.date, cluster_id) -> None:
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
        summary_sql = summary_sql.decode('utf-8')
        summary_sql_params = {
            'uuid': str(uuid.uuid4()).replace('-', '_'),
            'start_date': start_date,
            'end_date': end_date,
            'cluster_id': cluster_id,
            'schema': self.schema
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(
            summary_sql, summary_sql_params
        )
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params))

    def populate_storage_line_item_daily_summary_table(self, start_date: datetime.date,
                                                       end_date: datetime.date, cluster_id) -> None:
        """Populate the daily aggregate of storage line items table.

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
            'sql/reporting_ocpstoragelineitem_daily_summary.sql'
        )
        summary_sql = summary_sql.decode('utf-8')
        summary_sql_params = {
            'uuid': str(uuid.uuid4()).replace('-', '_'),
            'start_date': start_date,
            'end_date': end_date,
            'cluster_id': cluster_id,
            'schema': self.schema
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(
            summary_sql, summary_sql_params
        )
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, list(summary_sql_params))

    def update_summary_infrastructure_cost(self, cluster_id, start_date: datetime.date,
                                           end_date: datetime.date) -> None:
        """Populate the infrastructure costs on the daily usage summary table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP['line_item_daily_summary']
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
            summary_sql = summary_sql.decode('utf-8')
            summary_sql_params = {
                'uuid': str(uuid.uuid4()).replace('-', '_'),
                'start_date': start_date,
                'end_date': end_date,
                'cluster_id': cluster_id,
                'schema': self.schema
            }
            summary_sql, summary_sql_params = self.jinja_sql.prepare_query(
                summary_sql, summary_sql_params)
            self._execute_raw_sql_query(
                table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params))

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
        agg_sql = agg_sql.decode('utf-8')
        agg_sql_params = {'schema': self.schema}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(
            agg_sql, agg_sql_params
        )
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    # pylint: disable=invalid-name
    def populate_volume_claim_label_summary_table(self):
        """Populate the OCP volume claim label summary table."""
        table_name = OCP_REPORT_TABLE_MAP['volume_claim_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpstoragevolumeclaimlabel_summary.sql'
        )
        agg_sql = agg_sql.decode('utf-8')
        agg_sql_params = {'schema': self.schema}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(
            agg_sql, agg_sql_params
        )
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    # pylint: disable=invalid-name
    def populate_volume_label_summary_table(self):
        """Populate the OCP volume label summary table."""
        table_name = OCP_REPORT_TABLE_MAP['volume_label_summary']

        agg_sql = pkgutil.get_data(
            'masu.database',
            f'sql/reporting_ocpstoragevolumelabel_summary.sql'
        )
        agg_sql = agg_sql.decode('utf-8')
        agg_sql_params = {'schema': self.schema}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(
            agg_sql, agg_sql_params
        )
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_markup_cost(self, infra_provider_markup, ocp_markup, cluster_id):
        """Set markup cost for OCP including infrastructure cost markup."""
        with schema_context(self.schema):
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).update(
                markup_cost=(
                    (
                        Coalesce(
                            F('pod_charge_cpu_core_hours'),
                            Value(0, output_field=DecimalField())
                        )
                        + Coalesce(
                            F('pod_charge_memory_gigabyte_hours'),
                            Value(0, output_field=DecimalField())
                        )
                        + Coalesce(
                            F('persistentvolumeclaim_charge_gb_month'),
                            Value(0, output_field=DecimalField())
                        )

                    ) * ocp_markup
                    + (
                        Coalesce(
                            F('infra_cost'),
                            Value(0, output_field=DecimalField())
                        )
                    ) * infra_provider_markup
                )
            )
            OCPUsageLineItemDailySummary.objects.filter(cluster_id=cluster_id).update(
                project_markup_cost=(
                    (
                        Coalesce(
                            F('pod_charge_cpu_core_hours'),
                            Value(0, output_field=DecimalField())
                        )
                        + Coalesce(
                            F('pod_charge_memory_gigabyte_hours'),
                            Value(0, output_field=DecimalField())
                        )
                        + Coalesce(
                            F('persistentvolumeclaim_charge_gb_month'),
                            Value(0, output_field=DecimalField())
                        )

                    ) * ocp_markup
                    + (
                        Coalesce(F('project_infra_cost'), Value(0, output_field=DecimalField()))
                    ) * infra_provider_markup
                )
            )

    # pylint: disable=too-many-arguments
    def populate_monthly_cost(self, node_cost, start_date: datetime.date, end_date: datetime.date, cluster_id, cluster_alias):  # noqa: E501
        """
        Populate the monthly cost of a customer.

        Right now this is just the node/month cost. Calculated from
        node_cost * number_unique_nodes.

        args:
            node_cost (Decimal): The node cost per month
            start_date (datetime.date): The start_date to calculate monthly_cost.
            end_date (datetime.date): The end_date to calculate monthly_cost.

        """
        if not start_date:
            # If start_date is not provided, recalculate from the first month
            start_date = OCPUsageLineItemDailySummary.objects.aggregate(
                Min('usage_start')
            )['usage_start__min'].date()
        if not end_date:
            # If end_date is not provided, recalculate till the latest month
            end_date = OCPUsageLineItemDailySummary.objects.aggregate(
                Max('usage_end')
            )['usage_end__max'].date()

        first_month = start_date.replace(day=1)

        with schema_context(self.schema):
            # Calculate monthly cost for every month
            for curr_month in rrule(freq=MONTHLY, until=end_date, dtstart=first_month):
                first_curr_month, first_next_month = month_date_range_tuple(curr_month)
                LOG.info('Populating Monthly node cost from %s to %s.',
                         first_curr_month, first_next_month)

                unique_nodes = OCPUsageLineItemDailySummary.objects.\
                    filter(usage_start__gte=first_curr_month,
                           usage_start__lt=first_next_month,
                           cluster_id=cluster_id,
                           node__isnull=False
                           ).values_list('node').distinct()

                report_period = self.get_usage_period_by_dates_and_cluster(first_curr_month,
                                                                           first_next_month,
                                                                           cluster_id)

                for node in unique_nodes:
                    LOG.info('Node (%s) has a monthly cost of %s.', node[0], node_cost)
                    # delete node cost per month
                    OCPUsageLineItemDailySummary.objects.\
                        filter(usage_start=first_curr_month,
                               usage_end=first_curr_month,
                               monthly_cost=node_cost,
                               report_period=report_period,
                               cluster_id=cluster_id,
                               cluster_alias=cluster_alias,
                               monthly_cost__isnull=False,
                               node=node[0]).delete()
                    # add node cost per month
                    OCPUsageLineItemDailySummary.objects.create(
                        usage_start=first_curr_month,
                        usage_end=first_curr_month,
                        monthly_cost=node_cost,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        node=node[0])

    def remove_monthly_cost(self):
        """Delete all the monthly costs of a customer."""
        # start_date should be the first month this ocp was used
        start_date = OCPUsageLineItemDailySummary.objects.aggregate(
            Min('usage_start')
        )['usage_start__min']
        # If end_date is not provided, recalculate till the latest month
        end_date = OCPUsageLineItemDailySummary.objects.aggregate(
            Max('usage_end')
        )['usage_end__max']

        LOG.info('Removing monthly costs from %s to %s.', start_date, end_date)

        first_month = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        with schema_context(self.schema):
            # Calculate monthly cost for every month
            for curr_month in rrule(freq=MONTHLY, until=end_date, dtstart=first_month):
                first_curr_month, _ = month_date_range_tuple(curr_month)

                # Remove existing monthly costs
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start=first_curr_month,
                    monthly_cost__isnull=False
                ).delete()
