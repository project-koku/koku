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
"""Test the CostModelDBAccessor utility object."""
import random

from tenant_schemas.utils import schema_context

from api.metrics import constants as metric_constants
from api.models import Provider
from cost_models.models import CostModel
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator


def build_rates():
    """Returns rate_list to use to build cost model and mapping of expected values."""
    # Get defaults from constants.py
    cost_type_defaults = dict()
    for metric in metric_constants.COST_MODEL_METRIC_MAP:
        cost_type_defaults[metric["metric"]] = metric["default_cost_type"]
    mapping = dict()
    rates = []
    metric_names = [
        "cpu_core_usage_per_hour",
        "memory_gb_usage_per_hour",
        "cpu_core_request_per_hour",
        "memory_gb_request_per_hour",
        "storage_gb_usage_per_month",
        "storage_gb_request_per_month",
        "node_cost_per_month",
    ]
    duplicates_per_cost_type = 2
    for metric_name in metric_names:
        for cost_type in ["Infrastructure", "Supplementary"]:
            mapping_total = []
            for idx in range(duplicates_per_cost_type):
                value = round(random.uniform(1, 5), 2)
                mapping_total.append(value)
                rate = {"metric": {"name": metric_name}, "tiered_rates": [{"value": value, "unit": "USD"}]}
                # For testing the default cost type
                if cost_type != cost_type_defaults.get(metric_name):
                    rate["cost_type"] = cost_type
                rates.append(rate)
            if mapping.get(metric_name):
                original_mapping = mapping[metric_name]
                original_mapping[cost_type] = sum(mapping_total)
            else:
                mapping[metric_name] = {cost_type: sum(mapping_total)}
    return rates, mapping


class CostModelDBAccessorTest(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = self.ocp_provider_uuid
        self.schema = "acct10001"
        self.creator = ReportObjectCreator(self.schema)

        reporting_period = self.creator.create_ocp_report_period(provider_uuid=self.provider_uuid)
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_node_label_line_item(reporting_period, report)
        self.rates, self.expected_value_rate_mapping = build_rates()
        self.markup = {"value": 10, "unit": "percent"}
        self.cost_model = self.creator.create_cost_model(
            self.provider_uuid, Provider.PROVIDER_OCP, self.rates, self.markup
        )

    def test_initializer(self):
        """Test initializer."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            self.assertEqual(cost_model_accessor.provider_uuid, self.provider_uuid)

    def test_get_rates(self):
        """Test get rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            cpu_usage_rate = cost_model_accessor.get_rates("cpu_core_usage_per_hour")
            self.assertEqual(type(cpu_usage_rate), dict)

            mem_usage_rate = cost_model_accessor.get_rates("memory_gb_usage_per_hour")
            self.assertEqual(type(mem_usage_rate), dict)

            cpu_request_rate = cost_model_accessor.get_rates("cpu_core_request_per_hour")
            self.assertEqual(type(cpu_request_rate), dict)

            mem_request_rate = cost_model_accessor.get_rates("memory_gb_request_per_hour")
            self.assertEqual(type(mem_request_rate), dict)

            storage_usage_rate = cost_model_accessor.get_rates("storage_gb_usage_per_month")
            self.assertEqual(type(storage_usage_rate), dict)

            storage_request_rate = cost_model_accessor.get_rates("storage_gb_request_per_month")
            self.assertEqual(type(storage_request_rate), dict)

            storage_request_rate = cost_model_accessor.get_rates("node_cost_per_month")
            self.assertEqual(type(storage_request_rate), dict)

            missing_rate = cost_model_accessor.get_rates("wrong_metric")
            self.assertIsNone(missing_rate)

    def test_get_cpu_core_usage_per_hour_rates(self):
        """Test get cpu usage rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            cpu_rates = cost_model_accessor.get_cpu_core_usage_per_hour_rates()
            self.assertEqual(type(cpu_rates), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = cpu_rates.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["cpu_core_usage_per_hour"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_get_memory_gb_usage_per_hour_rates(self):
        """Test get memory usage rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            mem_rates = cost_model_accessor.get_memory_gb_usage_per_hour_rates()
            self.assertEqual(type(mem_rates), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = mem_rates.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["memory_gb_usage_per_hour"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_get_cpu_core_request_per_hour_rates(self):
        """Test get cpu request rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            cpu_rates = cost_model_accessor.get_cpu_core_request_per_hour_rates()
            self.assertEqual(type(cpu_rates), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = cpu_rates.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["cpu_core_request_per_hour"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_get_memory_gb_request_per_hour_rates(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            mem_rates = cost_model_accessor.get_memory_gb_request_per_hour_rates()
            self.assertEqual(type(mem_rates), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = mem_rates.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["memory_gb_request_per_hour"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_get_storage_gb_usage_per_month_rates(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            storage_rates = cost_model_accessor.get_storage_gb_usage_per_month_rates()
            self.assertEqual(type(storage_rates), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = storage_rates.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["storage_gb_usage_per_month"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_get_storage_gb_request_per_month_rates(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            storage_rates = cost_model_accessor.get_storage_gb_request_per_month_rates()
            self.assertEqual(type(storage_rates), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = storage_rates.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["storage_gb_request_per_month"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_markup(self):
        """Test to make sure markup dictionary is returned."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            self.assertEqual(markup, self.markup)
            markup = cost_model_accessor.markup
            self.assertEqual(markup, self.markup)

    def test_get_cost_model(self):
        """Test to make sure cost_model is gotten."""
        with schema_context(self.schema):
            model = CostModel.objects.filter(costmodelmap__provider_uuid=self.provider_uuid).first()
            uuid = model.uuid
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            self.assertEqual(cost_model_accessor.cost_model, model)
            self.assertEqual(cost_model_accessor.cost_model.uuid, uuid)

    def test_get_node_cost_per_month(self):
        """Test get memory request rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            node_cost = cost_model_accessor.get_node_per_month_rates()
            self.assertEqual(type(node_cost), dict)
            for cost_type in ["Infrastructure", "Supplementary"]:
                value_result = node_cost.get("tiered_rates", {}).get(cost_type, {})[0].get("value", 0)
                expected_value = self.expected_value_rate_mapping["node_cost_per_month"][cost_type]
                self.assertEqual(value_result, expected_value)

    def test_infrastructure_rates(self):
        """Test infrastructure rates property."""
        cost_type = "Infrastructure"
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            result_infra_rates = cost_model_accessor.infrastructure_rates
            for metric_name in result_infra_rates.keys():
                expected_value = self.expected_value_rate_mapping[metric_name][cost_type]
                self.assertEqual(result_infra_rates[metric_name], expected_value)

    def test_supplementary_rates(self):
        """Test supplementary rates property."""
        cost_type = "Supplementary"
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            result_sup_rates = cost_model_accessor.supplementary_rates
            for metric_name in result_sup_rates.keys():
                expected_value = self.expected_value_rate_mapping[metric_name][cost_type]
                self.assertEqual(result_sup_rates[metric_name], expected_value)


class CostModelDBAccessorTestNoRateOrMarkup(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = self.ocp_provider_uuid
        self.creator = ReportObjectCreator(self.schema)

        reporting_period = self.creator.create_ocp_report_period(self.ocp_provider_uuid)
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_node_label_line_item(reporting_period, report)

        self.cost_model = self.creator.create_cost_model(self.provider_uuid, Provider.PROVIDER_OCP)

    def test_initializer_no_rate_no_markup(self):
        """Test initializer."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            self.assertEqual(cost_model_accessor.provider_uuid, self.provider_uuid)

    def test_get_rates(self):
        """Test get rates."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            cpu_usage_rate = cost_model_accessor.get_rates("cpu_core_usage_per_hour")
            self.assertIsNone(cpu_usage_rate)


class CostModelDBAccessorNoCostModel(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = "3c6e687e-1a09-4a05-970c-2ccf44b0952e"
        self.schema = "acct10001"

    def test_get_rates_no_cost_model(self):
        """Test that get_rates returns empty dict when cost model does not exist."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            cpu_usage_rate = cost_model_accessor.get_rates("cpu_core_usage_per_hour")
            self.assertFalse(cpu_usage_rate)

    def test_markup_no_cost_model(self):
        """Test that markup returns empty dict when cost model does not exist."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            self.assertFalse(markup)


class CostModelDBAccessorTagRatesTest(MasuTestCase):
    """Test Cases for the CostModelDBAccessor object with tag rates."""

    KEY_VALUE_PAIRS = {
        "breakfast": ["pancakes", "waffles", "syrup"],
        "lunch": ["soup", "salad", "sandwich"],
        "dinner": ["steak", "chicken", "tacos"],
    }

    def build_tag_rates(self):
        """Returns rate_list to use to build cost model and mapping of expected values."""
        # Get defaults from constants.py
        cost_type_defaults = dict()
        for metric in metric_constants.COST_MODEL_METRIC_MAP:
            cost_type_defaults[metric["metric"]] = metric["default_cost_type"]
        mapping = dict()
        rates = []
        metric_names = [
            "cpu_core_usage_per_hour",
            "memory_gb_usage_per_hour",
            "cpu_core_request_per_hour",
            "memory_gb_request_per_hour",
            "storage_gb_usage_per_month",
            "storage_gb_request_per_month",
            "node_cost_per_month",
        ]
        mapping = {}
        for metric_name in metric_names:
            cost_type = random.choice(["Infrastructure", "Supplementary"])
            tag_key_dict = {}
            tag_vals_list = []
            default_other_keys = []
            tag_key = random.choice(list(self.KEY_VALUE_PAIRS))
            tag_vals = self.KEY_VALUE_PAIRS.get(tag_key)
            map_vals = {}
            for idx, tag_value_name in enumerate(tag_vals[0:2]):
                value = round(random.uniform(1, 5), 2)
                if idx == 0:
                    default = True
                    default_value = value
                else:
                    default = False
                default_other_keys.append(tag_value_name)
                map_vals[tag_value_name] = value
                val_dict = {"tag_value": tag_value_name, "value": value, "default": default}
                tag_vals_list.append(val_dict)
            tag_key_dict = {"tag_key": tag_key, "tag_values": tag_vals_list}
            rate = {"metric": {"name": metric_name}, "tag_rates": [tag_key_dict], "cost_type": cost_type}
            rates.append(rate)
            mapping[metric_name] = {
                "tag_key": tag_key,
                "cost_type": cost_type,
                "tag_values": map_vals,
                "default_value": default_value,
                "default_other_keys": default_other_keys,
            }
        return rates, mapping

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider_uuid = self.ocp_provider_uuid
        self.schema = "acct10001"
        self.creator = ReportObjectCreator(self.schema)

        reporting_period = self.creator.create_ocp_report_period(provider_uuid=self.provider_uuid)
        report = self.creator.create_ocp_report(reporting_period)
        self.creator.create_ocp_usage_line_item(reporting_period, report)
        self.creator.create_ocp_node_label_line_item(reporting_period, report)
        self.rates, self.mapping = self.build_tag_rates()
        self.cost_model = self.creator.create_cost_model(self.provider_uuid, Provider.PROVIDER_OCP, self.rates)

    def test_initializer(self):
        """Test initializer."""
        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            self.assertEqual(cost_model_accessor.provider_uuid, self.provider_uuid)

    def test_infrastructure_tag_rates(self):
        """Test infrastructure rates property."""
        cost_type = "Infrastructure"

        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            result_infra_rates = cost_model_accessor.tag_infrastructure_rates
            for metric_name in result_infra_rates.keys():
                expected_key = self.mapping.get(metric_name).get("tag_key")
                expected_vals = self.mapping.get(metric_name).get("tag_values")
                expected_cost_type = self.mapping.get(metric_name).get("cost_type")
                expected_dict = {expected_key: expected_vals}
                self.assertEqual(result_infra_rates.get(metric_name), expected_dict)
                self.assertEqual(expected_cost_type, cost_type)

    def test_supplementary_tag_rates(self):
        """Test supplementary rates property."""
        cost_type = "Supplementary"

        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            result_infra_rates = cost_model_accessor.tag_supplementary_rates
            for metric_name in result_infra_rates.keys():
                expected_key = self.mapping.get(metric_name).get("tag_key")
                expected_vals = self.mapping.get(metric_name).get("tag_values")
                expected_cost_type = self.mapping.get(metric_name).get("cost_type")
                expected_dict = {expected_key: expected_vals}
                self.assertEqual(result_infra_rates.get(metric_name), expected_dict)
                self.assertEqual(expected_cost_type, cost_type)

    def test_default_infrastructure_rates(self):
        """Tests that the proper keys and values are added for the default rates"""
        cost_type = "Infrastructure"

        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            result_infra_rates = cost_model_accessor.tag_default_infrastructure_rates
            for metric_name in result_infra_rates.keys():
                expected_key = self.mapping.get(metric_name).get("tag_key")
                expected_default_value = self.mapping.get(metric_name).get("default_value")
                expected_default_keys = self.mapping.get(metric_name).get("default_other_keys")
                expected_cost_type = self.mapping.get(metric_name).get("cost_type")
                expected_dict = {
                    expected_key: {"default_value": expected_default_value, "defined_keys": expected_default_keys}
                }
                self.assertEqual(result_infra_rates.get(metric_name), expected_dict)
                self.assertEqual(expected_cost_type, cost_type)

    def test_default_supplementary_rates(self):
        """Tests that the proper keys and values are added for the default rates"""
        cost_type = "Supplementary"

        with CostModelDBAccessor(self.schema, self.provider_uuid) as cost_model_accessor:
            result_infra_rates = cost_model_accessor.tag_default_supplementary_rates
            for metric_name in result_infra_rates.keys():
                expected_key = self.mapping.get(metric_name).get("tag_key")
                expected_default_value = self.mapping.get(metric_name).get("default_value")
                expected_default_keys = self.mapping.get(metric_name).get("default_other_keys")
                expected_cost_type = self.mapping.get(metric_name).get("cost_type")
                expected_dict = {
                    expected_key: {"default_value": expected_default_value, "defined_keys": expected_default_keys}
                }
                self.assertEqual(result_infra_rates.get(metric_name), expected_dict)
                self.assertEqual(expected_cost_type, cost_type)
