#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for OCP rate data."""
import copy
import logging
from collections import defaultdict

from django.db import transaction

from api.metrics import constants as metric_constants
from cost_models.models import CostModel

LOG = logging.getLogger(__name__)


class CostModelDBAccessor:
    """Class to interact with customer reporting tables."""

    cost_model_metric_map = metric_constants.get_cost_model_metrics_map()

    def __init__(self, schema, provider_uuid):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
            provider_uuid (str): Provider uuid

        """
        self.schema = schema
        self.provider_uuid = provider_uuid
        self._cost_model = None

    def __enter__(self):
        """Enter context manager."""
        connection = transaction.get_connection()
        connection.set_schema(self.schema)
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager reset schema to public and exit."""
        connection = transaction.get_connection()
        connection.set_schema_to_public()

    @property
    def cost_model(self):
        """Return the cost model database object."""
        if self._cost_model is None:
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
                default_metric = self.cost_model_metric_map[metric_name]
                metric_cost_type = default_metric["default_cost_type"]
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

    @property
    def distribution_info(self):
        """Returns distribution info field in the cost model."""
        if self.cost_model:
            return self.cost_model.distribution_info
        return {}

    def get_rates(self, value):
        """Get the rates."""
        return self.price_list.get(value)

    @property
    def metric_to_tag_params_map(self):
        """Returns the tag rate parameters"""
        if not self.cost_model:
            return {}
        tag_rate_list = []
        all_rates = copy.deepcopy(self.cost_model.rates)
        for rate in all_rates:
            tag_rate_param = {}
            tag_rate = rate.get("tag_rates")
            if not tag_rate:
                continue
            metric_name = rate.get("metric", {}).get("name")
            default_cost_type = self.cost_model_metric_map[metric_name]["default_cost_type"]
            tag_rate_param["rate_type"] = rate.get("cost_type", default_cost_type)
            tag_rate_param["tag_key"] = tag_rate.get("tag_key")
            kv_pairs_rates = {}
            for tag_value in tag_rate.get("tag_values"):
                if tag_value.get("default"):
                    tag_rate_param["default_rate"] = float(tag_value.get("value"))
                else:
                    kv_pairs_rates[tag_value.get("tag_value")] = float(tag_value.get("value"))
            if kv_pairs_rates:
                tag_rate_param["value_rates"] = kv_pairs_rates
            tag_rate_list.append({metric_name: tag_rate_param})
        metric_map = defaultdict(list)
        for item in tag_rate_list:
            for metric_name, params in item.items():
                metric_map[metric_name].append(params)
        return metric_map

    @property  # noqa: C901
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
                default_metric = self.cost_model_metric_map[metric_name]
                metric_cost_type = default_metric["default_cost_type"]
            tag_rates_list = []
            tag = rate.get("tag_rates")
            tag_rate_dict = {}
            tag_key = tag.get("tag_key")
            default_rate = 0
            for tag_rate in tag.get("tag_values"):
                rate_value = float(tag_rate.get("value"))
                unit = tag_rate.get("unit")
                default = tag_rate.get("default")
                if default:
                    default_rate = rate_value
                tag_value = tag_rate.get("tag_value")
                tag_rate_dict[tag_value] = {"unit": unit, "value": rate_value, "default": default}
            tag_rates_list.append({"tag_key": tag_key, "tag_values": tag_rate_dict, "tag_key_default": default_rate})
            if metric_name in metric_rate_map.keys():
                tag_rates = metric_rate_map.get(metric_name)
                existing_cost_dict = tag_rates.get("tag_rates")
                if existing_cost_dict.get(metric_cost_type):
                    existing_list = existing_cost_dict.get(metric_cost_type)
                    existing_list.extend(tag_rates_list)
                    existing_cost_dict[f"{metric_cost_type}"] = existing_list
                else:
                    existing_cost_dict[f"{metric_cost_type}"] = tag_rates_list
                    tag_rates["tag_rates"] = existing_cost_dict
                    metric_rate_map[metric_name] = tag_rates
            else:
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
                    'default_value': <value>, 'defined_keys': [values, to, be, ignored]
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
                    # NOTE: defined keys is actually list of values that have a rate associated with them.
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
                    'default_value': <value>, 'defined_keys': [values, to, be, ignored]
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
                    # Note: defined_keys is actually a list of tag values that have a specific rate
                    tag_dict[tag_key] = {"default_value": default_value, "defined_keys": tag_keys_to_ignore}
                    results_dict[key] = tag_dict
        return results_dict
