#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Update reporting summary tables."""
# pylint: skip-file

import datetime
import logging

from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.external.date_accessor import DateAccessor
from masu.processor.aws.aws_report_summary_updater import AWSReportSummaryUpdater
from masu.processor.ocp.ocp_cloud_summary_updater import OCPCloudReportSummaryUpdater
from masu.processor.ocp.ocp_report_summary_updater import OCPReportSummaryUpdater

LOG = logging.getLogger(__name__)


class ReportSummaryUpdaterError(Exception):
    """Expired Data Removalerror."""

    pass


# pylint: disable=too-few-public-methods
class ReportSummaryUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider (str): The provider type.
        """
        self._schema = customer_schema
        self._provider_uuid = provider_uuid
        self._date_accessor = DateAccessor()
        with ProviderDBAccessor(self._provider_uuid) as provider_accessor:
            self._provider = provider_accessor.get_type()
        try:
            self._updater, self._ocp_cloud_updater = self._set_updater()
        except Exception as err:
            raise ReportSummaryUpdaterError(err)

        if not self._updater:
            raise ReportSummaryUpdaterError('Invalid provider type specified.')

    def _set_updater(self):
        """
        Create the report summary updater object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report summary updater

        """
        if self._provider in (AMAZON_WEB_SERVICES, AWS_LOCAL_SERVICE_PROVIDER):
            return (AWSReportSummaryUpdater(self._schema),
                    OCPCloudReportSummaryUpdater(self._schema))
        if self._provider in (OPENSHIFT_CONTAINER_PLATFORM,
                              OCP_LOCAL_SERVICE_PROVIDER):
            return (OCPReportSummaryUpdater(self._schema),
                    OCPCloudReportSummaryUpdater(self._schema))

        return None

    def update_summary_tables(self, start_date, end_date, manifest_id=None):
        """
        Update provider report summary tables.

        Args:
            None

        Returns:
            None

        """
        if isinstance(start_date, datetime.date):
            start_date = start_date.strftime('%Y-%m-%d')
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime('%Y-%m-%d')
        elif end_date is None:
            # Run up to the current date
            end_date = self._date_accessor.today_with_timezone('UTC')
            end_date = end_date.strftime('%Y-%m-%d')
        LOG.info('Using start date: %s', start_date)
        LOG.info('Using end date: %s', end_date)

        start_date, end_date = self._updater.update_summary_tables(
            start_date,
            end_date,
            self._provider_uuid,
            manifest_id
        )

        self._ocp_cloud_updater.update_summary_tables(
            start_date,
            end_date,
            self._provider_uuid,
            manifest_id
        )
