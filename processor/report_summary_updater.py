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

import logging

from masu.external import (AMAZON_WEB_SERVICES,
                           AWS_LOCAL_SERVICE_PROVIDER,
                           OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.processor.aws.aws_report_summary_updater import AWSReportSummaryUpdater
from masu.processor.ocp.ocp_report_summary_updater import OCPReportSummaryUpdater

LOG = logging.getLogger(__name__)


class ReportSummaryUpdaterError(Exception):
    """Expired Data Removalerror."""

    pass


# pylint: disable=too-few-public-methods
class ReportSummaryUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider (str): The provider type.
        """
        self._schema = customer_schema
        self._provider = provider
        try:
            self._updater = self._set_updater()
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
            return AWSReportSummaryUpdater(self._schema)
        if self._provider in (OPENSHIFT_CONTAINER_PLATFORM,
                              OCP_LOCAL_SERVICE_PROVIDER):
            return OCPReportSummaryUpdater(self._schema)

        return None

    def update_summary_tables(self, start_date, end_date, manifest_id=None):
        """
        Remove expired data based on the retention policy.

        Args:
            None

        Returns:
            None

        """
        self._updater.update_summary_tables(start_date, end_date, manifest_id)
