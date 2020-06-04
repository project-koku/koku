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
"""Update Cost Model Cost info for report summary tables."""
import logging

from api.models import Provider
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.aws.aws_cost_model_cost_updater import AWSCostModelCostUpdater
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater

LOG = logging.getLogger(__name__)


class CostModelCostUpdaterError(Exception):
    """Expired Data Removalerror."""


class CostModelCostUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider_uuid (str): The provider uuid.

        """
        self._schema = customer_schema

        with ProviderDBAccessor(provider_uuid) as provider_accessor:
            self._provider = provider_accessor.get_provider()
        try:
            self._updater = self._set_updater()
        except Exception as err:
            raise CostModelCostUpdaterError(err)

    def _set_updater(self):
        """
        Create the report charge updater object.

        Object is specific to the report provider.

        Args:
            None

        Returns:
            (Object) : Provider-specific report summary updater

        """
        if self._provider is None:
            return None

        if self._provider.type in (Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL):
            return AWSCostModelCostUpdater(self._schema, self._provider)
        if self._provider.type in (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL):
            return AzureCostModelCostUpdater(self._schema, self._provider)
        if self._provider.type in (Provider.PROVIDER_OCP,):
            return OCPCostModelCostUpdater(self._schema, self._provider)

        return None

    def update_cost_model_costs(self, start_date=None, end_date=None):
        """
        Update usage charge information.

        Args:
            start_date (String) - Start date of range to update derived cost.
            end_date (String) - End date of range to update derived cost.

        Returns:
            None

        """
        if self._updater:
            self._updater.update_summary_cost_model_costs(start_date, end_date)
            invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)
