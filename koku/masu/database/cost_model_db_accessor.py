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
"""Database accessor for OCP rate data."""
import logging

from tenant_schemas.utils import schema_context

from cost_models.models import CostModel
from masu.database.koku_database_access import KokuDBAccess

LOG = logging.getLogger(__name__)


class CostModelDBAccessor(KokuDBAccess):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema, provider_uuid):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            provider_uuid (str): Provider uuid

        """
        super().__init__(schema)
        self.provider_uuid = provider_uuid
        self._cost_model = None

    @property
    def cost_model(self):
        """Return the cost model database object."""
        if self._cost_model is None:
            with schema_context(self.schema):
                self._cost_model = CostModel.objects.filter(costmodelmap__provider_uuid=self.provider_uuid).first()
        return self._cost_model

    @property
    def price_list(self):
        """Return the rates definied on this cost model."""
        metric_rate_map = {}
        price_list = None
        if self.cost_model:
            price_list = self.cost_model.rates
        if not price_list:
            return {}
        for rate in price_list:
            metric_rate_map[rate.get("metric", {}).get("name")] = rate
        return metric_rate_map

    @property
    def infrastructure_rates(self):
        """Return the rates designated as infrastructure cost."""
        return {
            key: value.get("tiered_rates")[0].get("value")
            for key, value in self.price_list.items()
            if value.get("cost_type") == "Infrastructure"
        }

    @property
    def supplementary_rates(self):
        """Return the rates designated as infrastructure cost."""
        return {
            key: value.get("tiered_rates")[0].get("value")
            for key, value in self.price_list.items()
            if value.get("cost_type") == "Supplementary"
        }

    @property
    def markup(self):
        if self.cost_model:
            return self.cost_model.markup
        return {}

    def get_rates(self, value):
        """Get the rates."""
        return self.price_list.get(value)

    def get_cpu_core_usage_per_hour_rates(self):
        """Get cpu usage rates."""
        cpu_usage_rates = self.get_rates("cpu_core_usage_per_hour")
        LOG.info("OCP CPU usage rates: %s", str(cpu_usage_rates))
        return cpu_usage_rates

    def get_memory_gb_usage_per_hour_rates(self):
        """Get the memory usage rates."""
        mem_usage_rates = self.get_rates("memory_gb_usage_per_hour")
        LOG.info("OCP Memory usage rates: %s", str(mem_usage_rates))
        return mem_usage_rates

    def get_cpu_core_request_per_hour_rates(self):
        """Get cpu request rates."""
        cpu_request_rates = self.get_rates("cpu_core_request_per_hour")
        LOG.info("OCP CPU request rates: %s", str(cpu_request_rates))
        return cpu_request_rates

    def get_memory_gb_request_per_hour_rates(self):
        """Get the memory request rates."""
        mem_request_rates = self.get_rates("memory_gb_request_per_hour")
        LOG.info("OCP Memory request rates: %s", str(mem_request_rates))
        return mem_request_rates

    def get_storage_gb_usage_per_month_rates(self):
        """Get the storage usage rates."""
        storage_usage_rates = self.get_rates("storage_gb_usage_per_month")
        LOG.info("OCP Storage usage rates: %s", str(storage_usage_rates))
        return storage_usage_rates

    def get_storage_gb_request_per_month_rates(self):
        """Get the storage request rates."""
        storage_request_rates = self.get_rates("storage_gb_request_per_month")
        LOG.info("OCP Storage request rates: %s", str(storage_request_rates))
        return storage_request_rates

    def get_node_per_month_rates(self):
        """Get the storage request rates."""
        node_rates = self.get_rates("node_cost_per_month")
        LOG.info("OCP Node rate: %s", str(node_rates))
        return node_rates
