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
import datetime
import logging

from tenant_schemas.utils import schema_context

from masu.database.aws_report_db_accessor import AWSReportDBAccessor
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.reporting_common_db_accessor import ReportingCommonDBAccessor
from masu.external import AMAZON_WEB_SERVICES, AWS_LOCAL_SERVICE_PROVIDER, OPENSHIFT_CONTAINER_PLATFORM
from masu.external.date_accessor import DateAccessor
from masu.util.aws.common import get_bills_from_provider
from masu.util.ocp.common import get_cluster_id_from_provider

LOG = logging.getLogger(__name__)


class OCPCloudReportSummaryUpdater:
    """Class to update OCP report summary data."""

    def __init__(self, schema, provider, manifest):
        """Establish the database connection.

        Args:
            schema   (str) The customer schema to associate with.
            provider (Provider db object) Database object for Provider.
            manifest (str) The manifest to work with.

        Returns:
            None

        """
        self._schema_name = schema
        self._provider = provider
        self._manifest = manifest
        with ReportingCommonDBAccessor() as reporting_common:
            self._column_map = reporting_common.column_map
        self._date_accessor = DateAccessor()

    def _get_ocp_infra_map(self, start_date, end_date):
        """Get the OCP on X infrastructure map.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns:
            infra_map (list) The OCP infrastructure map.

        """
        infra_map = None
        with OCPReportDBAccessor(self._schema_name, self._column_map) as accessor:
            infra_map = accessor.get_ocp_infrastructure_map(start_date, end_date)
        return infra_map

    def _get_infra_db_key_for_provider_type(self, provider_type):
        """Get infrastructure map provider key.

        Args:
            provider_type (str) The provider

        Returns:
            db_key (str) The infrastructure map provider key

        """
        if provider_type in (AMAZON_WEB_SERVICES, AWS_LOCAL_SERVICE_PROVIDER):
            db_key = 'aws_uuid'
        elif provider_type in (OPENSHIFT_CONTAINER_PLATFORM):
            db_key = 'ocp_uuid'
        else:
            db_key = None
        return db_key

    def _get_ocp_cluster_id_for_provider(self, provider, start_date, end_date, infra_map):
        """Get the OCP cluster-id for given OCP-on-AWS provider configuration.

        When provider is AWS it will return the OCP cluster id if one exists.
        When provider is OCP it will return the OCP cluster id if it is running on AWS.

        Args:
            provider   (Provider db object).  Database object for Provider.
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.
            infra_map  (DB Object) Map from OCPReportDBAccessor().get_ocp_infrastructure_map()

        Returns
            cluster_id (str) OCP cluster ID.

        """
        db_key = self._get_infra_db_key_for_provider_type(provider.type)
        if db_key:
            for entry in infra_map:
                if provider.uuid == entry.get(db_key):
                    return entry.get('cluster_id')
        return None

    def _get_aws_provider_uuid_from_map(self, provider, infra_map):
        """Get the AWS provider UUID for given OCP-on-AWS provider configuration.

        When provider is AWS it will return the AWS provider uuid if OCP is running on it.
        When provider is OCP it will return the AWS provider uuid if AWS is the infrastructure.

        Args:
            provider   (Provider db object).  Database object for Provider.
            infra_map  (DB Object) Map from OCPReportDBAccessor().get_ocp_infrastructure_map()

        Returns
            provider_uuid (str) AWS provider uuid.

        """
        db_key = self._get_infra_db_key_for_provider_type(provider.type)
        if db_key:
            for entry in infra_map:
                if provider.uuid == entry.get(db_key):
                    return entry.get('aws_uuid')
        return None

    def update_summary_tables(self, start_date, end_date):
        """Populate the summary tables for reporting.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            None

        """
        infra_map = self._get_ocp_infra_map(start_date, end_date)
        cluster_id = self._get_ocp_cluster_id_for_provider(self._provider, start_date, end_date, infra_map)
        if cluster_id:
            aws_uuid = self._get_aws_provider_uuid_from_map(self._provider, infra_map)
            aws_bills = get_bills_from_provider(
                aws_uuid,
                self._schema_name,
                datetime.datetime.strptime(start_date, '%Y-%m-%d'),
                datetime.datetime.strptime(end_date, '%Y-%m-%d')
            )
            aws_bill_ids = []
            with schema_context(self._schema_name):
                aws_bill_ids = [str(bill.id) for bill in aws_bills]

            with CostModelDBAccessor(self._schema_name, aws_uuid,
                                     self._column_map) as cost_model_accessor:
                markup = cost_model_accessor.get_markup()
                markup_value = float(markup.get('value', 0)) / 100

            # OpenShift on AWS
            with AWSReportDBAccessor(self._schema_name, self._column_map) as accessor:
                LOG.info('Updating OpenShift on AWS summary table for '
                         '\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s'
                         '\n\tCluster ID: %s, AWS Bill IDs: %s',
                         self._schema_name, self._provider.uuid,
                         start_date, end_date, cluster_id, str(aws_bill_ids))
                accessor.populate_ocp_on_aws_cost_daily_summary(
                    start_date,
                    end_date,
                    cluster_id,
                    aws_bill_ids
                )
                accessor.populate_ocp_on_aws_markup_cost(markup_value, aws_bill_ids)
        else:
            LOG.info('Provider: %s is not part of an OCP-on-AWS configuration.', self._provider.name)

    def update_cost_summary_table(self, start_date, end_date):
        """Populate the cost summary tables.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            None

        """
        cluster_id = get_cluster_id_from_provider(self._provider.uuid)
        # This needs to always run regardless of whether the OpenShift
        # cluster is tied to a cloud provider
        infra_map = self._get_ocp_infra_map(start_date, end_date)
        aws_uuid = self._get_aws_provider_uuid_from_map(self._provider, infra_map)
        with CostModelDBAccessor(self._schema_name, aws_uuid,
                                 self._column_map) as cost_model_accessor:
            markup = cost_model_accessor.get_markup()
            aws_markup_value = float(markup.get('value', 0)) / 100
        with CostModelDBAccessor(self._schema_name, self._provider.uuid,
                                 self._column_map) as cost_model_accessor:
            markup = cost_model_accessor.get_markup()
            ocp_markup_value = float(markup.get('value', 0)) / 100

        with OCPReportDBAccessor(self._schema_name, self._column_map) as accessor:
            LOG.info('Updating OpenShift on OCP cost summary table for'
                     '\n\tSchema: %s \n\tProvider: %s \n\tDates: %s - %s',
                     self._schema_name, self._provider.uuid, start_date, end_date)
            accessor.populate_cost_summary_table(cluster_id, start_date, end_date)
            accessor.populate_ocp_on_aws_markup_cost(aws_markup_value, ocp_markup_value, cluster_id)
