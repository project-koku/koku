#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Update Cost Model Cost info for report summary tables."""
import logging

from api.models import Provider
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.aws.aws_cost_model_cost_updater import AWSCostModelCostUpdater
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.processor.gcp.gcp_cost_model_cost_updater import GCPCostModelCostUpdater
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
        if self._provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            return GCPCostModelCostUpdater(self._schema, self._provider)

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
