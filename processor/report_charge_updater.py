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
"""Update charge info for report summary tables."""

import logging

from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external import (OCP_LOCAL_SERVICE_PROVIDER,
                           OPENSHIFT_CONTAINER_PLATFORM)
from masu.processor.ocp.ocp_report_charge_updater import OCPReportChargeUpdater

LOG = logging.getLogger(__name__)


class ReportChargeUpdaterError(Exception):
    """Expired Data Removalerror."""

    pass


# pylint: disable=too-few-public-methods
class ReportChargeUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider_uuid (str): The provider uuid.
        """
        self._schema = customer_schema
        self._provider_uuid = provider_uuid
        self._provider = ProviderDBAccessor(provider_uuid).get_type()
        try:
            self._updater = self._set_updater()
        except Exception as err:
            raise ReportChargeUpdaterError(err)

    def _set_updater(self):
        """
        Create the report charge updater object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report summary updater

        """
        if self._provider in (OPENSHIFT_CONTAINER_PLATFORM,
                              OCP_LOCAL_SERVICE_PROVIDER):
            return OCPReportChargeUpdater(self._schema, self._provider_uuid)

        return None

    def update_charge_info(self):
        """
        Update usage charge information.

        Args:
            None

        Returns:
            None

        """
        if self._updater:
            self._updater.update_summary_charge_info()
            self._updater.close_session()
