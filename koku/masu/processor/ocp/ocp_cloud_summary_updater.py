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
"""Updates report summary tables in the database."""
# pylint: skip-file

import logging

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.util.aws.common import get_bills_from_provider
from masu.util.ocp.common import get_cluster_id_from_provider

LOG = logging.getLogger(__name__)


class OCPCloudReportSummaryUpdater:
    """Class to update OCP report summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        self._schema_name = schema
        self._provider = provider
        self._manifest = manifest
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map
        self._date_accessor = DateAccessor()

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            None

        """
        cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        aws_bills = get_bills_from_provider(
            self._provider.uuid,
            self._schema_name,
            start_date,
            end_date
        )
        aws_bill_ids = [str(bill.id) for bill in aws_bills]
        # OpenShift on AWS
        with AWSReportDBAccessor(self._schema_name, self._column_map) as accessor:
            LOG.info('Updating OpenShift on AWS summary table for '
                     '\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s',
                     self._schema_name, self._provider.uuid, start_date, end_date)
            accessor.populate_ocp_on_aws_cost_daily_summary(
                start_date,
                end_date,
                cluster_id,
                aws_bill_ids
            )
            accessor.commit()

        if cluster_id:
            with OCPReportDBAccessor(self._schema_name, self._column_map) as accessor:
                LOG.info('Updating OpenShift on OCP cost summary table for'
                         '\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s',
                         self._schema_name, self._provider.uuid, start_date, end_date)
                accessor.populate_cost_summary_table(cluster_id, start_date, end_date)
                accessor.commit()
