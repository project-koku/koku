#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Cost Model serializers."""
from pydantic import ValidationError

from api.metrics import constants as metric_constants
from cost_models.sql_parameters import VMParams
from masu.test import MasuTestCase


class CostModelSQLParameterTest(MasuTestCase):
    """Tests for Cost Model Manager."""

    def test_invalid_dates(self):
        with self.assertRaises(ValidationError):
            VMParams(
                schema=self.schema_name,
                start_date=self.dh.this_month_end.date(),
                end_date=self.dh.this_month_start.date(),
                source_uuid=self.ocp_provider_uuid,
                report_period_id=1,
            )

    def test_key_value_pair(self):
        """Test no default value response."""
        tag_price_list = {
            metric_constants.OCP_VM_MONTH: {
                "metric": {"name": "vm_cost_per_hour"},
                "tag_rates": {
                    "Supplementary": [
                        {
                            "tag_key": "group",
                            "tag_values": {
                                "Engineering": {
                                    "unit": "USD",
                                    "value": 0.05,
                                    "default": False,
                                }
                            },
                            "tag_key_default": 0,
                        }
                    ]
                },
            }
        }
        params = VMParams(
            schema=self.schema_name,
            start_date=self.dh.this_month_start.date(),
            end_date=self.dh.this_month_end.date(),
            source_uuid=self.ocp_provider_uuid,
            report_period_id=1,
        )
        result_params = params.build_tag_based_rate_parameters(tag_price_list, metric_constants.OCP_VM_MONTH)
        param_dict = result_params[0]
        self.assertEqual(param_dict.get("value_rates"), {"Engineering": 0.05})
        self.assertEqual(param_dict.get("tag_key"), "group")
        self.assertIsNone(param_dict.get("default_rate"))

    def test_default_rate(self):
        """Test default rate only response."""
        tag_price_list = {
            metric_constants.OCP_VM_HOUR: {
                "metric": {"name": "vm_cost_per_hour"},
                "tag_rates": {
                    "Supplementary": [
                        {
                            "tag_key": "group",
                            "tag_values": {
                                "Engineering": {
                                    "unit": "USD",
                                    "value": 0.05,
                                    "default": True,
                                }
                            },
                            "tag_key_default": 0.05,
                        }
                    ]
                },
            }
        }
        params = VMParams(
            schema=self.schema_name,
            start_date=self.dh.this_month_start.date(),
            end_date=self.dh.this_month_end.date(),
            source_uuid=self.ocp_provider_uuid,
            report_period_id=1,
        )
        result_params = params.build_tag_based_rate_parameters(tag_price_list, metric_constants.OCP_VM_HOUR)
        param_dict = result_params[0]
        self.assertIsNone(param_dict.get("value_rates"))
        self.assertEqual(param_dict.get("tag_key"), "group")
        self.assertEqual(param_dict.get("default_rate"), 0.05)

    def test_no_tag_based_rates(self):
        """Test no tag based rates"""
        tag_price_list = {}
        params = VMParams(
            schema=self.schema_name,
            start_date=self.dh.this_month_start.date(),
            end_date=self.dh.this_month_end.date(),
            source_uuid=self.ocp_provider_uuid,
            report_period_id=1,
        )
        result_params = params.build_tag_based_rate_parameters(tag_price_list, metric_constants.OCP_VM_HOUR)
        self.assertIsNone(result_params)
