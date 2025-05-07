#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Update Cost Model Cost info for report summary tables."""
import datetime

import ciso8601

from api.models import Provider
from api.utils import DateHelper
from koku.cache import invalidate_cache_for_tenant_and_cache_key
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from koku.cache import TAG_MAPPING_PREFIX
from masu.processor import is_customer_cost_model_large
from masu.processor.aws.aws_cost_model_cost_updater import AWSCostModelCostUpdater
from masu.processor.azure.azure_cost_model_cost_updater import AzureCostModelCostUpdater
from masu.processor.gcp.gcp_cost_model_cost_updater import GCPCostModelCostUpdater
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater


class CostModelCostUpdaterError(Exception):
    """Expired Data Removalerror."""


class CostModelCostUpdater:
    """Update reporting summary tables."""

    def __init__(self, customer_schema, provider_uuid, tracing_id=None):
        """
        Initializer.

        Args:
            customer_schema (str): Schema name for given customer.
            provider_uuid (str): The provider uuid.

        """
        self._schema = customer_schema
        self.tracing_id = tracing_id

        self._provider = Provider.objects.filter(uuid=provider_uuid).first()
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
        if not self._provider:
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

    def _format_dates(self, start_date, end_date):
        """Convert dates to strings for use in the updater."""
        if isinstance(start_date, datetime.date):
            start_date = start_date.strftime("%Y-%m-%d")
        elif isinstance(start_date, str):
            start_date = ciso8601.parse_datetime(start_date).date()
        if isinstance(end_date, datetime.date):
            end_date = end_date.strftime("%Y-%m-%d")
        elif isinstance(end_date, str):
            end_date = ciso8601.parse_datetime(end_date).date()
        return start_date, end_date

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
            if is_customer_cost_model_large(self._schema):
                for day_date in DateHelper().list_days(start_date, end_date):
                    start, end = self._format_dates(day_date, day_date)
                    self._updater.update_summary_cost_model_costs(start, end)
            else:
                start_date, end_date = self._format_dates(start_date, end_date)
                self._updater.update_summary_cost_model_costs(start_date, end_date)
            invalidate_view_cache_for_tenant_and_source_type(self._schema, self._provider.type)
            # Invalidate the tag_rate_map for tag mapping
            invalidate_cache_for_tenant_and_cache_key(self._schema, TAG_MAPPING_PREFIX)
