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
"""Removes report data from database."""

import logging

from tenant_schemas.utils import schema_context

from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor

LOG = logging.getLogger(__name__)


class OCPReportDBCleanerError(Exception):
    """Raise an error during OCP report cleaning."""


# pylint: disable=too-few-public-methods
class OCPReportDBCleaner():
    """Class to remove report data."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        self._schema = schema

    # pylint: disable=too-many-locals
    def purge_expired_report_data(self, expired_date=None, provider_id=None,
                                  simulate=False):
        """Remove usage data with a report period before specified date.

        Args:
            expired_date (datetime.datetime): The cutoff date for removing data.
            provider_id (str): The DB id of the provider to purge data for.
            simulate (bool): Whether to simluate the removal.

        Returns:
            ([{}]) List of dictionaries containing 'usage_period_id' and 'interval_start'

        """
        with ReportingCommonDBAccessor() as reporting_common:
            column_map = reporting_common.column_map

        with OCPReportDBAccessor(self._schema, column_map) as accessor:
            if ((expired_date is not None and provider_id is not None) or  # noqa: W504
                    (expired_date is None and provider_id is None)):
                err = 'This method must be called with expired_date or provider_id'
                raise OCPReportDBCleanerError(err)
            removed_items = []

            if expired_date is not None:
                usage_period_objs = accessor.get_usage_period_before_date(expired_date)
            else:
                usage_period_objs = accessor.get_usage_period_query_by_provider(provider_id)
            with schema_context(self._schema):
                for usage_period in usage_period_objs.all():
                    report_period_id = usage_period.id
                    cluster_id = usage_period.cluster_id
                    removed_usage_start_period = usage_period.report_period_start

                    if not simulate:
                        qty = accessor.get_item_query_report_period_id(report_period_id).delete()
                        LOG.info('Removing %s usage period line items for usage period id %s',
                                 qty, report_period_id)

                        qty = accessor.get_daily_usage_query_for_clusterid(cluster_id).delete()
                        LOG.info('Removing %s usage daily items for cluster id %s',
                                 qty, cluster_id)

                        qty = accessor.get_summary_usage_query_for_clusterid(cluster_id).delete()
                        LOG.info('Removing %s usage summary items for cluster id %s',
                                 qty, cluster_id)

                        qty = accessor.get_cost_summary_for_clusterid(cluster_id).delete()
                        LOG.info('Removing %s cost summary items for cluster id %s',
                                 qty, cluster_id)

                        qty = accessor.get_storage_item_query_report_period_id(report_period_id).\
                            delete()
                        LOG.info('Removing %s storage line items for usage period id %s',
                                 qty, report_period_id)

                        qty = accessor.get_daily_storage_item_query_cluster_id(cluster_id).\
                            delete()
                        LOG.info('Removing %s storage dailyitems for cluster id %s',
                                 qty, cluster_id)

                        qty = accessor.get_storage_summary_query_cluster_id(cluster_id).\
                            delete()
                        LOG.info('Removing %s storage summary for cluster id %s',
                                 qty, cluster_id)

                        qty = accessor.get_report_query_report_period_id(report_period_id).delete()
                        LOG.info('Removing %s usage period items for usage period id %s',
                                 qty, report_period_id)

                        qty = accessor.get_ocp_aws_summary_query_for_cluster_id(cluster_id).delete()
                        LOG.info('Removing %s OCP-on-AWS summary items for cluster id %s',
                                 qty, cluster_id)
                        # pylint: disable=line-too-long
                        qty = accessor.get_ocp_aws_project_summary_query_for_cluster_id(cluster_id).\
                            delete()
                        LOG.info('Removing %s OCP-on-AWS project summary items for cluster id %s',
                                 qty, cluster_id)

                    LOG.info('Report data removed for usage period ID: %s with interval start: %s',
                             report_period_id, removed_usage_start_period)
                    removed_items.append({'usage_period_id': report_period_id,
                                          'interval_start': str(removed_usage_start_period)})

                if not simulate:
                    usage_period_objs.delete()
        return removed_items
