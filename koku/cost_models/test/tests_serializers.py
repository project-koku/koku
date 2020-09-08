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
"""Test the Cost Model serializers."""
import logging
import random
from decimal import Decimal

import faker
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.metrics.constants import SOURCE_TYPE_MAP
from api.provider.models import Provider
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.serializers import CostModelSerializer
from cost_models.serializers import UUIDKeyRelatedField

LOG = logging.getLogger(__name__)


def format_tag_value(**kwarg_dict):
    """Returns a tag_value."""
    return {
        "tag_value": kwarg_dict.get("tag_value", "value_one"),
        "unit": kwarg_dict.get("unit", "USD"),
        "usage": {
            "unit": kwarg_dict.get("unit", "USD"),
            "usage_end": kwarg_dict.get("usage_end", None),
            "usage_start": kwarg_dict.get("usage_start", None),
        },
        "value": kwarg_dict.get("value", 0.2),
        "description": kwarg_dict.get("description", ""),
        "default": kwarg_dict.get("default", False),
    }


def format_tag_rate(tag_key="key_one", tag_values=None):
    """Returns a tag_rate."""
    final_tag_values = []
    if tag_values:
        for tag_value_kwarg in tag_values:
            final_tag_values.append(format_tag_value(**tag_value_kwarg))
    else:
        if tag_values == []:
            final_tag_values = tag_values
        else:
            final_tag_values = [format_tag_value(**{})]
    return {"tag_key": tag_key, "tag_values": final_tag_values}


class CostModelSerializerTest(IamTestCase):
    """Cost Model serializer tests."""

    fake = faker.Faker()

    def setUp(self):
        """Set up the tests."""
        super().setUp()

        self.provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()

        ocp_metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        ocp_source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        self.ocp_data = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": ocp_source_type,
            "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
            "markup": {"value": 10, "unit": "percent"},
            "rates": [{"metric": {"name": ocp_metric}, "tiered_rates": tiered_rates}],
        }
        self.basic_model = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
            "markup": {"value": 10, "unit": "percent"},
            "rates": [{"metric": {"name": ocp_metric}}],
        }

    def tearDown(self):
        """Clean up test cases."""
        with tenant_context(self.tenant):
            CostModel.objects.all().delete()
            CostModelMap.objects.all().delete()

    def test_valid_data(self):
        """Test rate and markup for valid entries."""
        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.assertIn(instance.source_type, SOURCE_TYPE_MAP.keys())
            self.assertIsNotNone(instance.markup)
            self.assertIsNotNone(instance.rates)

    def test_uuid_key_related_field(self):
        """Test the uuid key related field."""
        uuid_field = UUIDKeyRelatedField(queryset=Provider.objects.all(), pk_field="uuid")
        self.assertFalse(uuid_field.use_pk_only_optimization())
        self.assertEqual(self.provider.uuid, uuid_field.to_internal_value(self.provider.uuid))
        self.assertEqual(self.provider.uuid, uuid_field.to_representation(self.provider))
        self.assertEqual(self.provider.uuid, uuid_field.display_value(self.provider))

    def test_error_on_invalid_provider(self):
        """Test error with an invalid provider id."""
        self.ocp_data.update({"source_uuids": ["1dd7204c-72c4-4ec4-95bc-d5c447688b27"]})
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_not_OCP_source_type_with_markup(self):
        """Test that a source type is valid if it has markup."""
        self.ocp_data["source_type"] = Provider.PROVIDER_AWS
        self.ocp_data["rates"] = []

        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.assertIsNotNone(instance)
            self.assertIsNotNone(instance.markup)

    def test_error_source_type_with_markup(self):
        """Test that non-existent source type is invalid."""
        self.ocp_data["source_type"] = "invalid-source"

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_source_type_without_markup(self):
        """Test error when non OCP source is added without markup."""
        self.ocp_data["source_type"] = Provider.PROVIDER_AWS
        self.ocp_data["markup"] = {}
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_nonOCP_source_type_with_markup_and_rates(self):
        """Test error when non OCP source is added with markup and rates."""
        self.ocp_data["source_type"] = Provider.PROVIDER_AWS

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_invalid_metric(self):
        """Test error on an invalid metric rate."""
        self.ocp_data.get("rates", [])[0]["metric"]["name"] = "invalid_metric"
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_usage_bad_start_bound(self):
        """Test error on a usage_start that does not cover lower bound."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {"usage_start": 5, "usage_end": None}

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_usage_bad_upper_bound(self):
        """Test error on a usage_end that does not cover lower bound."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {"usage_start": None, "usage_end": 5}

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_rate_type(self):
        """Test error when trying to create an invalid rate input."""
        self.ocp_data["rates"][0].pop("tiered_rates")
        self.ocp_data["rates"][0]["bad_rates"] = []
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_negative_rate(self):
        """Test error when trying to create an negative rate input."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["value"] = float(round(Decimal(random.random()), 6) * -1)

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_no_rate(self):
        """Test error when trying to create an empty rate."""
        self.ocp_data["rates"][0]["tiered_rates"] = []

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_usage_start(self):
        """Test error when trying to create a negative tiered usage_start."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {
            "usage_start": float(round(Decimal(random.random()), 6) * -1),
            "usage_end": 20.0,
        }
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_usage_end(self):
        """Test error when trying to create a negative tiered usage_end."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {
            "usage_start": 10.0,
            "usage_end": float(round(Decimal(random.random()), 6) * -1),
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_tier_usage_end_less_than(self):
        """Test error when trying to create a tiered usage_end less than usage_start."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {"usage_start": 10.0, "usage_end": 3.0}

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_create_cpu_core_per_hour_tiered_rate(self):
        """Test creating a cpu_core_per_hour rate."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {"unit": "USD", "value": 0.22, "usage": {"usage_start": None, "usage_end": 10.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 10.0, "usage_end": None}},
        ]

        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertIsNotNone(instance)
            self.assertIsNotNone(instance.uuid)

    def test_tiered_rate_null_start_end(self):
        """Test creating a rate with out a start and end."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {"unit": "USD", "value": 0.22, "usage": {"usage_start": 0.0, "usage_end": 7.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 10.0, "usage_end": 20.0}},
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_tiered_rate_with_gaps(self):
        """Test creating a tiered rate with a gap between the tiers."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {"unit": "USD", "value": 0.22, "usage": {"usage_start": None, "usage_end": 7.0}},
            {"unit": "USD", "value": 0.26, "usage_start": 10.0, "usage_end": None},
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_create_storage_tiered_rate(self):
        """Test creating a storage tiered rate."""
        storage_rates = (
            metric_constants.OCP_METRIC_STORAGE_GB_REQUEST_MONTH,
            metric_constants.OCP_METRIC_STORAGE_GB_USAGE_MONTH,
        )
        for storage_rate in storage_rates:
            ocp_data = {
                "name": "Test Cost Model",
                "description": "Test",
                "source_type": Provider.PROVIDER_OCP,
                "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
                "rates": [
                    {
                        "metric": {"name": storage_rate},
                        "tiered_rates": [
                            {"unit": "USD", "value": 0.22, "usage": {"usage_start": None, "usage_end": 10.0}},
                            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 10.0, "usage_end": None}},
                        ],
                    }
                ],
            }

            with tenant_context(self.tenant):
                instance = None
                serializer = CostModelSerializer(data=ocp_data)
                if serializer.is_valid(raise_exception=True):
                    instance = serializer.save()
                self.assertIsNotNone(instance)
                self.assertIsNotNone(instance.uuid)

    def test_create_storage_no_tiers_rate(self):
        """Test creating a non tiered storage rate."""
        storage_rates = (
            metric_constants.OCP_METRIC_STORAGE_GB_REQUEST_MONTH,
            metric_constants.OCP_METRIC_STORAGE_GB_USAGE_MONTH,
        )
        for storage_rate in storage_rates:
            ocp_data = {
                "name": "Test Cost Model",
                "description": "Test",
                "source_type": Provider.PROVIDER_OCP,
                "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
                "rates": [{"metric": {"name": storage_rate}, "tiered_rates": [{"unit": "USD", "value": 0.22}]}],
            }

            with tenant_context(self.tenant):
                instance = None
                serializer = CostModelSerializer(data=ocp_data)
                if serializer.is_valid(raise_exception=True):
                    instance = serializer.save()
                self.assertIsNotNone(instance)
                self.assertIsNotNone(instance.uuid)

    def test_tiered_rate_with_overlaps(self):
        """Test creating a tiered rate with a overlaps between the tiers."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {"unit": "USD", "value": 0.22, "usage": {"usage_start": None, "usage_end": 10.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 5.0, "usage_end": 20.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 20.0, "usage_end": None}},
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_tiered_rate_with_duplicate(self):
        """Test creating a tiered rate with duplicate tiers."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {"unit": "USD", "value": 0.22, "usage": {"usage_start": None, "usage_end": 10.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 10.0, "usage_end": 20.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 10.0, "usage_end": 20.0}},
            {"unit": "USD", "value": 0.26, "usage": {"usage_start": 20.0, "usage_end": None}},
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_get_metric_display_data_openshift(self):
        """Test the display data helper function for OpenShift metrics."""
        serializer = CostModelSerializer(data=None)

        for metric_choice in metric_constants.METRIC_CHOICES:
            response = serializer._get_metric_display_data(Provider.PROVIDER_OCP, metric_choice[0])
            self.assertIsNotNone(response.get("label_measurement_unit"))
            self.assertIsNotNone(response.get("label_measurement"))
            self.assertIsNotNone(response.get("label_metric"))

    def test_validate_rates_allows_duplicate_metric(self):
        """Check that duplicate rate types for a metric are rejected."""
        rate = self.ocp_data["rates"][0]
        expected_metric_name = rate.get("metric", {}).get("name")
        expected_metric_count = 2
        self.assertIsNotNone(expected_metric_name)
        # Add another tiered rate entry for the same metric
        self.ocp_data["rates"].append(rate)
        result_metric_count = 0
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            valid_rates = serializer.validate_rates(self.ocp_data["rates"])
            for valid_rate in valid_rates:
                if valid_rate.get("metric", {}).get("name") == expected_metric_name:
                    result_metric_count += 1
        self.assertEqual(expected_metric_count, result_metric_count)

    def test_rate_cost_type_valid(self):
        """Test that a valid cost type is accepted."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {
                "unit": "USD",
                "value": 0.22,
                "usage": {"usage_start": None, "usage_end": None},
                "cost_type": "Infrastructure",
            }
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

        self.ocp_data["rates"][0]["tiered_rates"] = [
            {
                "unit": "USD",
                "value": 0.22,
                "usage": {"usage_start": None, "usage_end": None},
                "cost_type": "Supplementary",
            }
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_rate_cost_type_invalid(self):
        """Test that an invalid cost type is rejected."""
        self.ocp_data["rates"][0]["cost_type"] = "Infrastructurez"

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_multiple_tag_values_marked_as_default(self):
        """Test that multiple default set to true fails."""
        tag_values_kwargs = [{"default": True}, {"tag_value": "value_two", "value": 0.3, "default": True}]
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=tag_values_kwargs)]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        print(serializer.errors)
        result_err_msg = serializer.errors["rates"][0]["tag_values"][0]
        expected_err_msg = "Only one tag_value per tag_key can be marked as a default."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_negitive_tag_value(self):
        """Test that a negivite value in the tag value fails."""
        tag_values_kwargs = [{"value": -0.2}]
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=tag_values_kwargs)]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["value"][0]
        expected_err_msg = "A tag rate value must be positive."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_negitive_usage_start(self):
        """Test that a negivite usage_start for tag_rates fails."""
        tag_values_kwargs = [{"usage_start": -5}]
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=tag_values_kwargs)]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["usage"][0]
        expected_err_msg = "A tag rate usage_start must be positive."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_negitive_usage_end(self):
        """Test that a negivite usage_end for tag_rates fails."""
        tag_values_kwargs = [{"usage_end": -5}]
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=tag_values_kwargs)]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["usage"][0]
        expected_err_msg = "A tag rate usage_end must be positive."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_usage_start_greater_than_usage_end(self):
        """Test that usage_start greater than a usage end fails"""
        tag_values_kwargs = [{"usage_start": 10, "usage_end": 2}]
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=tag_values_kwargs)]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["usage"][0]
        expected_err_msg = "A tag rate usage_start must be less than usage_end."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_error_on_empty_list_for_tag_values(self):
        """Test that tag_values can not be an empty list."""
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=[])]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"][0]
        expected_err_msg = "A tag_values can not be an empty list."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_key_can_be_multiple_cost_types(self):
        """Test that tag keys can be multiple cost types."""
        value_kwargs = [{"value": 0.1, "default": True, "usage_start": 1, "usage_end": 10}]
        tag_rates_list = []
        cost_types = ["Infrastructure", "Supplementary"]
        for cost_type in cost_types:
            rate = {"metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR}, "cost_type": cost_type}
            rate["tag_rates"] = [format_tag_rate(tag_values=value_kwargs)]
            tag_rates_list.append(rate)
        self.basic_model["rates"] = tag_rates_list
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            serializer.save()
            data = serializer.data
        rates = data.get("rates", [])
        self.assertEqual(len(rates), 2)
        for rate in rates:
            tag_rates = rate.get("tag_rates")
            self.assertIsNotNone(tag_rates)
            # Check cost types
            result_cost_type = rate["cost_type"]
            self.assertIn(result_cost_type, cost_types)
            cost_types.remove(result_cost_type)
            for tag_rate in tag_rates:
                # Check that to_representation is working
                tag_value = tag_rate["tag_values"][0]
                decimals = [tag_value["value"], tag_value["usage"]["usage_start"], tag_value["usage"]["usage_end"]]
                for expected_decimal in decimals:
                    self.assertIsInstance(expected_decimal, Decimal)

    def test_multiple_tag_values(self):
        """Test that tag keys can be multiple cost types."""
        value_kwargs = [
            {"tag_value": "value_one", "value": 0.1, "default": True},
            {"tag_value": "value_two", "value": 0.2},
        ]
        self.basic_model["rates"][0]["tag_rates"] = [format_tag_rate(tag_values=value_kwargs)]
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            serializer.save()
            data = serializer.data
        rates = data["rates"]
        self.assertEqual(len(rates), 1)
        for rate in rates:
            tag_rates = rate.get("tag_rates")
            self.assertIsNotNone(tag_rates)
            for tag_rate in tag_rates:
                tag_values = tag_rate["tag_values"]
                self.assertEqual(len(tag_values), 2)
