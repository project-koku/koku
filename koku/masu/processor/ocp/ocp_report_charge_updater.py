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
"""Updates report summary tables in the database with charge information."""

import csv
import io
import logging
from decimal import Decimal

from tenant_schemas.utils import schema_context

from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.ocp.common import get_cluster_id_from_provider

LOG = logging.getLogger(__name__)


class OCPReportChargeUpdaterError(Exception):
    """OCPReportChargeUpdater error."""


# pylint: disable=too-few-public-methods
class OCPReportChargeUpdater:
    """Class to update OCP report summary data with charge information."""

    def __init__(self, schema, provider_uuid, provider_id):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map
        self._provider_uuid = provider_uuid
        self._cluster_id = None
        self._provider_id = provider_id

    @staticmethod
    def _normalize_tier(input_tier):
        # Pull out the parts for beginning, middle, and end for validation and ordering correction.
        first_tier = [t for t in input_tier if not t.get('usage', {}).get('usage_start')]
        last_tier = [t for t in input_tier if not t.get('usage', {}).get('usage_end')]
        middle_tiers = \
            [t for t in input_tier if
             t.get('usage', {}).get('usage_start') and t.get('usage', {}).get('usage_end')]

        # Ensure that there is only 1 starting tier. (i.e. 1 'usage_start': None, if provided)
        if not first_tier:
            LOG.error('Failed Tier: %s', str(input_tier))
            raise OCPReportChargeUpdaterError('Missing first tier.')

        if len(first_tier) != 1:
            LOG.error('Failed Tier: %s', str(input_tier))
            raise OCPReportChargeUpdaterError('Two starting tiers.')

        # Ensure that there is only 1 final tier. (i.e. 1 'usage_end': None, if provided)
        if not last_tier:
            LOG.error('Failed Tier: %s', str(input_tier))
            raise OCPReportChargeUpdaterError('Missing last tier.')

        if len(last_tier) != 1:
            LOG.error('Failed Tier: %s', str(input_tier))
            raise OCPReportChargeUpdaterError('Two final tiers.')

        # Remove last 'usage_end' for consistency to avoid 'usage_end: 0' situations.
        last_tier[0].pop('usage_end', None)

        # Build final tier that is sorted in asending order.
        newlist = first_tier
        newlist += sorted(middle_tiers, key=lambda k: k['usage']['usage_end'])
        newlist += last_tier

        return newlist

    @staticmethod
    def _bucket_applied(usage, lower_limit, upper_limit):
        usage_applied = 0

        if usage >= upper_limit:
            usage_applied = upper_limit
        elif usage > lower_limit:
            usage_applied = usage - lower_limit

        return usage_applied

    def _calculate_variable_charge(self, usage, rates):
        charge = Decimal(0)
        balance = usage
        tier = []
        if rates:
            tier = self._normalize_tier(rates.get('tiered_rates', []))

        for bucket in tier:
            usage_end = Decimal(bucket.get('usage', {}).get('usage_end')) \
                if bucket.get('usage', {}).get('usage_end') else None
            usage_start = Decimal(bucket.get('usage', {}).get('usage_start')) \
                if bucket.get('usage', {}).get('usage_start') else 0
            bucket_size = (usage_end - usage_start) if usage_end else None

            lower_limit = 0
            upper_limit = bucket_size
            rate = Decimal(bucket.get('value'))

            usage_applied = 0
            if upper_limit is not None:
                usage_applied = self._bucket_applied(balance, lower_limit, upper_limit)
            else:
                usage_applied = balance

            charge += usage_applied * rate
            balance -= usage_applied

        return Decimal(charge)

    def _calculate_charge(self, rates, usage):
        """Calculate charge based on rate and usage."""
        charge_dictionary = {}
        for key, value in usage.items():
            if not value:
                value = Decimal(0.0)
            charge_value = self._calculate_variable_charge(value, rates)
            charge_dictionary[key] = {'usage': value, 'charge': charge_value}
        return charge_dictionary

    @staticmethod
    def _aggregate_charges(usage_charge, request_charge):
        """Combine the usage and request charges."""
        if usage_charge.keys() != request_charge.keys():
            raise OCPReportChargeUpdaterError('Usage and request charge mismatched.')

        charge_dictionary = {}
        for key, value in usage_charge.items():
            usage_charge_value = value.get('charge')
            request_charge_value = request_charge[key].get('charge')
            charge_dictionary[key] = {'usage_charge': usage_charge_value,
                                      'request_charge': request_charge_value,
                                      'charge': usage_charge_value + request_charge_value}
        return charge_dictionary

    @staticmethod
    def _charge_dictionary_to_csv(charge_dictionary):
        """Write charge dictionary to a csv file_obj."""
        dictionary_data = []
        for key, value in charge_dictionary.items():
            line_item = (key, value.get('charge'))
            dictionary_data.append(line_item)

        file_obj = io.StringIO()
        writer = csv.writer(file_obj, delimiter='\t',
                            quoting=csv.QUOTE_NONE, quotechar='')
        writer.writerows(dictionary_data)
        file_obj.seek(0)

        return file_obj

    def _write_to_temp_table(self, report_accessor, charge_data):
        """Create temporary table to store charge."""
        columns = [{'lineid': 'bigint'}, {'charge': 'numeric(24,6)'}]
        temp_table = report_accessor.create_new_temp_table('charge', columns)
        csv_file = self._charge_dictionary_to_csv(charge_data)
        report_accessor.bulk_insert_rows(csv_file, temp_table, ['lineid', 'charge'])
        return temp_table

    def _update_markup_cost(self):
        """Store markup costs."""
        try:
            with CostModelDBAccessor(self._schema, self._provider_uuid,
                                     self._column_map) as cost_model_accessor:
                markup = cost_model_accessor.markups.get('value', 0) / 100

            with OCPReportDBAccessor(self._schema, self._column_map) as report_accessor:
                report_accessor.populate_markup_cost(markup, self._cluster_id)
        except OCPReportChargeUpdaterError as error:
            LOG.error('Unable to update markup costs. Error: %s', str(error))


    # pylint: disable=too-many-locals
    def _update_pod_charge(self):
        """Calculate and store total POD charges."""
        try:
            with CostModelDBAccessor(self._schema, self._provider_uuid,
                                     self._column_map) as cost_model_accessor:
                cpu_usage_rates = cost_model_accessor.get_cpu_core_usage_per_hour_rates()
                cpu_request_rates = cost_model_accessor.get_cpu_core_request_per_hour_rates()
                mem_usage_rates = cost_model_accessor.get_memory_gb_usage_per_hour_rates()
                mem_request_rates = cost_model_accessor.get_memory_gb_request_per_hour_rates()

            with OCPReportDBAccessor(self._schema, self._column_map) as report_accessor:
                try:
                    cpu_usage = report_accessor.get_pod_usage_cpu_core_hours(self._cluster_id)
                    cpu_usage_charge = self._calculate_charge(cpu_usage_rates, cpu_usage)

                    cpu_request = report_accessor.get_pod_request_cpu_core_hours(self._cluster_id)
                    cpu_request_charge = self._calculate_charge(cpu_request_rates, cpu_request)

                    total_cpu_charge = self._aggregate_charges(cpu_usage_charge, cpu_request_charge)
                except OCPReportChargeUpdaterError as error:
                    total_cpu_charge = {}
                    LOG.error('Unable to calculate cpu charge. Error: %s', str(error))

                cpu_temp_table = self._write_to_temp_table(report_accessor,
                                                           total_cpu_charge)

                try:
                    mem_usage = report_accessor.\
                        get_pod_usage_memory_gigabyte_hours(self._cluster_id)
                    mem_usage_charge = self._calculate_charge(mem_usage_rates, mem_usage)

                    mem_request = report_accessor.\
                        get_pod_request_memory_gigabyte_hours(self._cluster_id)
                    mem_request_charge = self._calculate_charge(mem_request_rates, mem_request)

                    total_memory_charge = self._aggregate_charges(mem_usage_charge,
                                                                  mem_request_charge)
                except OCPReportChargeUpdaterError as error:
                    total_memory_charge = {}
                    LOG.error('Unable to calculate memory charge. Error: %s', str(error))

                mem_temp_table = self._write_to_temp_table(report_accessor,
                                                           total_memory_charge)

                report_accessor.populate_pod_charge(cpu_temp_table, mem_temp_table)
        except OCPReportChargeUpdaterError as error:
            LOG.error('Unable to calculate charge. Error: %s', str(error))

    def _update_storage_charge(self):
        """Calculate and store the storage charges."""
        try:
            with CostModelDBAccessor(self._schema, self._provider_uuid,
                                     self._column_map) as cost_model_accessor:
                storage_usage_rates = cost_model_accessor.get_storage_gb_usage_per_month_rates()
                storage_request_rates = cost_model_accessor.get_storage_gb_request_per_month_rates()

            with OCPReportDBAccessor(self._schema, self._column_map) as report_accessor:
                storage_usage = report_accessor.\
                    get_persistentvolumeclaim_usage_gigabyte_months(self._cluster_id)
                storage_usage_charge = self._calculate_charge(storage_usage_rates,
                                                              storage_usage)

                storage_request = report_accessor.\
                    get_volume_request_storage_gigabyte_months(self._cluster_id)
                storage_request_charge = self._calculate_charge(storage_request_rates,
                                                                storage_request)
                total_storage_charge = self._aggregate_charges(storage_usage_charge,
                                                               storage_request_charge)
                temp_table = self._write_to_temp_table(report_accessor,
                                                       total_storage_charge)
                report_accessor.populate_storage_charge(temp_table)

        except OCPReportChargeUpdaterError as error:
            LOG.error('Unable to calculate storage usage charge. Error: %s', str(error))

    def update_summary_charge_info(self, start_date=None, end_date=None):
        """Update the OCP summary table with the charge information.

        Args:
            start_date (str, Optional) - Start date of range to update derived cost.
            end_date (str, Optional) - End date of range to update derived cost.

        Returns
            None

        """
        self._cluster_id = get_cluster_id_from_provider(self._provider_uuid)

        LOG.info('Starting charge calculation updates for provider: %s. Cluster ID: %s.',
                 self._provider_uuid, self._cluster_id)
        self._update_pod_charge()
        self._update_storage_charge()
        self._update_markup_cost()

        with OCPReportDBAccessor(self._schema, self._column_map) as accessor:
            report_periods = accessor.report_periods_for_provider_id(self._provider_id, start_date)
            with schema_context(self._schema):
                for period in report_periods:
                    period.derived_cost_datetime = DateAccessor().today_with_timezone('UTC')
                    period.save()
