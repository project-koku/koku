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
import copy
import logging

from tenant_schemas.utils import schema_context

from api.metrics import constants as metric_constants
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
            price_list = copy.deepcopy(self.cost_model.rates)
        if not price_list:
            return {}
        for rate in price_list:
            if not rate.get("tiered_rates"):
                continue
            metric_name = rate.get("metric", {}).get("name")
            metric_cost_type = rate.pop("cost_type", None)
            if not metric_cost_type:
                for default_metric in metric_constants.COST_MODEL_METRIC_MAP:
                    if metric_name == default_metric.get("metric"):
                        metric_cost_type = default_metric.get("default_cost_type")
            if metric_name in metric_rate_map.keys():
                metric_mapping = metric_rate_map.get(metric_name)
                if metric_cost_type in metric_mapping.get("tiered_rates", {}).keys():
                    current_tiered_mapping = metric_mapping.get("tiered_rates", {}).get(metric_cost_type)
                    new_tiered_rate = rate.get("tiered_rates")
                    current_value = float(current_tiered_mapping[0].get("value"))
                    value_to_add = float(new_tiered_rate[0].get("value"))
                    current_tiered_mapping[0]["value"] = current_value + value_to_add
                    metric_rate_map[metric_name] = metric_mapping
                else:
                    new_tiered_rate = rate.get("tiered_rates")
                    current_tiered_mapping = metric_mapping.get("tiered_rates", {})[metric_cost_type] = new_tiered_rate
            else:
                format_tiered_rates = {f"{metric_cost_type}": rate.get("tiered_rates")}
                rate["tiered_rates"] = format_tiered_rates
                metric_rate_map[metric_name] = rate
        self.tag_based_price_list.items()
        return metric_rate_map

    @property
    def infrastructure_rates(self):
        """Return the rates designated as infrastructure cost."""
        return {
            key: value.get("tiered_rates").get(metric_constants.INFRASTRUCTURE_COST_TYPE)[0].get("value")
            for key, value in self.price_list.items()
            if metric_constants.INFRASTRUCTURE_COST_TYPE in value.get("tiered_rates").keys()
        }

    @property
    def supplementary_rates(self):
        """Return the rates designated as supplementary cost."""
        return {
            key: value.get("tiered_rates").get(metric_constants.SUPPLEMENTARY_COST_TYPE)[0].get("value")
            for key, value in self.price_list.items()
            if metric_constants.SUPPLEMENTARY_COST_TYPE in value.get("tiered_rates").keys()
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

    @property
    def tag_based_price_list(self):  # noqa: C901
        """Return the rates definied on this cost model that come from tag based rates."""
        metric_rate_map = {}
        tag_based_price_list = None
        if self.cost_model:
            tag_based_price_list = copy.deepcopy(self.cost_model.rates)
        if not tag_based_price_list:
            return {}
        for rate in tag_based_price_list:
            if not rate.get("tag_rates"):
                continue
            metric_name = rate.get("metric", {}).get("name")
            metric_cost_type = rate.pop("cost_type", None)
            if not metric_cost_type:
                for default_metric in metric_constants.COST_MODEL_METRIC_MAP:
                    if metric_name == default_metric.get("metric"):
                        metric_cost_type = default_metric.get("default_cost_type")
            tag_rates_list = []
            for tag in rate.get("tag_rates"):
                tag_rate_dict = {}
                tag_key = tag.get("tag_key")
                default_rate = 0
                for tag_rate in tag.get("tag_values"):
                    rate_value = tag_rate.get("value")
                    unit = tag_rate.get("unit")
                    default = tag_rate.get("default")
                    if default:
                        default_rate = rate_value
                    tag_value = tag_rate.get("tag_value")
                    tag_rate_dict[tag_value] = {"unit": unit, "value": rate_value, "default": default}
                tag_rates_list.append(
                    {"tag_key": tag_key, "tag_values": tag_rate_dict, "tag_key_default": default_rate}
                )
            format_tag_rates = {f"{metric_cost_type}": tag_rates_list}
            rate["tag_rates"] = format_tag_rates
            metric_rate_map[metric_name] = rate
        return metric_rate_map

    @property
    def tag_infrastructure_rates(self):
        """
        Return the rates designated as infrastructure cost from tag based rates.
        The format for this is
        {
            metric: {
                tag_key: {
                    tag_value: value_rate, tag_value_2: value_rate
                }
            }
        }
        This is in order to keep tag values associated with their key
        """
        results_dict = {}
        for key, value in self.tag_based_price_list.items():
            if metric_constants.INFRASTRUCTURE_COST_TYPE in value.get("tag_rates").keys():
                tag_dict = {}
                for tag in value.get("tag_rates").get(metric_constants.INFRASTRUCTURE_COST_TYPE):
                    tag_key = tag.get("tag_key")
                    tag_values = {}
                    for value_key, val in tag.get("tag_values").items():
                        tag_values[value_key] = val.get("value")
                    tag_dict[tag_key] = tag_values
                    results_dict[key] = tag_dict
        return results_dict

    @property
    def tag_default_infrastructure_rates(self):
        """
        Return the default infrastructure rates for each key that has a defined rate
        It is returned in the format
        {
            metric: {
                key: {
                    'default_value': <value>, 'defined_keys': [keys, to, be, ignored]
                }
            }
        }
        Where the keys to be ignored is a list of tag values that have defined rates
        """
        results_dict = {}
        for key, value in self.tag_based_price_list.items():
            if metric_constants.INFRASTRUCTURE_COST_TYPE in value.get("tag_rates").keys():
                tag_dict = {}
                for tag in value.get("tag_rates").get(metric_constants.INFRASTRUCTURE_COST_TYPE):
                    tag_key = tag.get("tag_key")
                    tag_keys_to_ignore = list(tag.get("tag_values").keys())
                    default_value = tag.get("tag_key_default")
                    tag_dict[tag_key] = {"default_value": default_value, "defined_keys": tag_keys_to_ignore}
                    results_dict[key] = tag_dict
        return results_dict

    @property
    def tag_supplementary_rates(self):
        """
        Return the rates designated as supplementary cost from tag based rates.
        The format for this is
        {
            metric: {
                tag_key: {
                    tag_value: value_rate, tag_value_2: value_rate
                }
            }
        }
        This is in order to keep tag values associated with their key
        """
        results_dict = {}
        for key, value in self.tag_based_price_list.items():
            if metric_constants.SUPPLEMENTARY_COST_TYPE in value.get("tag_rates").keys():
                tag_dict = {}
                for tag in value.get("tag_rates").get(metric_constants.SUPPLEMENTARY_COST_TYPE):
                    tag_key = tag.get("tag_key")
                    tag_values = {}
                    for value_key, val in tag.get("tag_values").items():
                        tag_values[value_key] = val.get("value")
                    tag_dict[tag_key] = tag_values
                    results_dict[key] = tag_dict
        return results_dict

    @property
    def tag_default_supplementary_rates(self):
        """
        Return the default supplementary rates for each key that has a defined rate
        It is returned in the format
        {
            metric: {
                key: {
                    'default_value': <value>, 'defined_keys': [keys, to, be, ignored]
                }
            }
        }
        Where the keys to be ignored is a list of tag values that have defined rates
        """
        results_dict = {}
        for key, value in self.tag_based_price_list.items():
            if metric_constants.SUPPLEMENTARY_COST_TYPE in value.get("tag_rates").keys():
                tag_dict = {}
                for tag in value.get("tag_rates").get(metric_constants.SUPPLEMENTARY_COST_TYPE):
                    tag_key = tag.get("tag_key")
                    tag_keys_to_ignore = list(tag.get("tag_values").keys())
                    default_value = tag.get("tag_key_default")
                    tag_dict[tag_key] = {"default_value": default_value, "defined_keys": tag_keys_to_ignore}
                    results_dict[key] = tag_dict
        return results_dict
