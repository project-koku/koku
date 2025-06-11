#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Cost Model serializers."""
import random
from decimal import Decimal
from itertools import combinations
from itertools import product
from uuid import uuid4

import faker
from django_tenants.utils import tenant_context
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.metrics import constants as metric_constants
from api.metrics.constants import DEFAULT_DISTRIBUTION_INFO
from api.metrics.constants import SOURCE_TYPE_MAP
from api.provider.models import Provider
from api.utils import get_currency
from cost_models.models import CostModel
from cost_models.models import CostModelMap
from cost_models.serializers import CostModelSerializer
from cost_models.serializers import DistributionSerializer
from cost_models.serializers import RateSerializer
from cost_models.serializers import UUIDKeyRelatedField


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
            "currency": "USD",
        }
        self.basic_model = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
            "markup": {"value": 10, "unit": "percent"},
            "rates": [{"metric": {"name": ocp_metric}}],
            "currency": "USD",
        }

    def tearDown(self):
        """Clean up test cases."""
        with tenant_context(self.tenant):
            CostModel.objects.all().delete()
            CostModelMap.objects.all().delete()

    def test_valid_data(self):
        """Test rate and markup for valid entries."""
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            instance = serializer.save()
            self.assertIsNotNone(instance)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                serializer.is_valid(raise_exception=True)

    def test_not_OCP_source_type_with_markup(self):
        """Test that a source type is valid if it has markup."""
        self.ocp_data["source_type"] = Provider.PROVIDER_AWS
        self.ocp_data["rates"] = []

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            instance = serializer.save()
            self.assertIsNotNone(instance)
            self.assertIsNotNone(instance.markup)

    def test_error_source_type_with_markup(self):
        """Test that non-existent source type is invalid."""
        self.ocp_data["source_type"] = "invalid-source"

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_source_type_without_markup(self):
        """Test error when non OCP source is added without markup."""
        self.ocp_data["source_type"] = Provider.PROVIDER_AWS
        self.ocp_data["markup"] = {}
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_nonOCP_source_type_with_markup_and_rates(self):
        """Test error when non OCP source is added with markup and rates."""
        self.ocp_data["source_type"] = Provider.PROVIDER_AWS

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_invalid_metric(self):
        """Test error on an invalid metric rate."""
        self.ocp_data.get("rates", [])[0]["metric"]["name"] = "invalid_metric"
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_usage_bad_start_bound(self):
        """Test error on a usage_start that does not cover lower bound."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {"usage_start": 5, "usage_end": None}

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_usage_bad_upper_bound(self):
        """Test error on a usage_end that does not cover lower bound."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {"usage_start": None, "usage_end": 5}

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_rate_type(self):
        """Test error when trying to create an invalid rate input."""
        self.ocp_data["rates"][0].pop("tiered_rates")
        self.ocp_data["rates"][0]["bad_rates"] = []
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_negative_rate(self):
        """Test error when trying to create an negative rate input."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["value"] = float(round(Decimal(random.random()), 6) * -1)

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_no_rate(self):
        """Test error when trying to create an empty rate."""
        self.ocp_data["rates"][0]["tiered_rates"] = []

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_tier_usage_end_less_than(self):
        """Test error when trying to create a tiered usage_end less than usage_start."""
        self.ocp_data["rates"][0]["tiered_rates"][0]["usage"] = {"usage_start": 10.0, "usage_end": 3.0}

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
                "currency": "USD",
            }

            with tenant_context(self.tenant):
                instance = None
                serializer = CostModelSerializer(data=ocp_data, context=self.request_context)
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
                "currency": "USD",
            }

            with tenant_context(self.tenant):
                instance = None
                serializer = CostModelSerializer(data=ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_get_metric_display_data_openshift(self):
        """Test the display data helper function for OpenShift metrics."""
        serializer = CostModelSerializer(data=None)

        for metric_choice in metric_constants.STANDARD_METRIC_CHOICES:
            response = serializer._get_metric_display_data(Provider.PROVIDER_OCP, metric_choice)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
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
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                serializer.save()

    def test_rate_cost_type_invalid(self):
        """Test that an invalid cost type is rejected."""
        self.ocp_data["rates"][0]["cost_type"] = "Infrastructurez"

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_multiple_tag_values_marked_as_default(self):
        """Test that multiple default set to true fails."""
        tag_values_kwargs = [{"default": True}, {"tag_value": "value_two", "value": 0.3, "default": True}]
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        print(serializer.errors)
        result_err_msg = serializer.errors["rates"][0]["tag_values"][0]
        expected_err_msg = "Only one tag_value per tag_key can be marked as a default."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_negitive_tag_value(self):
        """Test that a negivite value in the tag value fails."""
        tag_values_kwargs = [{"value": -0.2}]
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["value"][0]
        expected_err_msg = "A tag rate value must be nonnegative."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_negitive_usage_start(self):
        """Test that a negivite usage_start for tag_rates fails."""
        tag_values_kwargs = [{"usage_start": -5}]
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["usage"][0]
        expected_err_msg = "A tag rate usage_start must be positive."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_negitive_usage_end(self):
        """Test that a negivite usage_end for tag_rates fails."""
        tag_values_kwargs = [{"usage_end": -5}]
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["usage"][0]
        expected_err_msg = "A tag rate usage_end must be positive."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_usage_start_greater_than_usage_end(self):
        """Test that usage_start greater than a usage end fails"""
        tag_values_kwargs = [{"usage_start": 10, "usage_end": 2}]
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["tag_values"]["usage"][0]
        expected_err_msg = "A tag rate usage_start must be less than usage_end."
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_error_on_empty_list_for_tag_values(self):
        """Test that tag_values can not be an empty list."""
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=[])
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
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
            rate["tag_rates"] = format_tag_rate(tag_values=value_kwargs)
            tag_rates_list.append(rate)
        self.basic_model["rates"] = tag_rates_list
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            serializer.save()
            data = serializer.data
        rates = data.get("rates", [])
        self.assertEqual(len(rates), 2)
        for rate in rates:
            tag_rate = rate.get("tag_rates")
            self.assertIsNotNone(tag_rate)
            # Check cost types
            result_cost_type = rate["cost_type"]
            self.assertIn(result_cost_type, cost_types)
            cost_types.remove(result_cost_type)
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
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=value_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            serializer.save()
            data = serializer.data
        rates = data["rates"]
        self.assertEqual(len(rates), 1)
        for rate in rates:
            tag_rate = rate.get("tag_rates")
            self.assertIsNotNone(tag_rate)
            tag_values = tag_rate["tag_values"]
            self.assertEqual(len(tag_values), 2)

    def test_rates_error_on_specifying_tiered_and_tag_rates(self):
        """Test that specifying both tiered and tag rates fails."""
        tag_values_kwargs = [{"value": 0.2}]
        tiered_rate = [{"value": 1.3, "unit": "USD"}]
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        self.basic_model["rates"][0]["tiered_rates"] = tiered_rate
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = serializer.errors["rates"][0]["non_field_errors"][0]
        expected_err_msg = "Set either 'tiered_rates' or 'tag_rates' but not both"
        self.assertEqual(result_err_msg, expected_err_msg)

    def test_tag_rates_error_on_duplicate_metric_per_cost_type(self):
        """Test duplicate key on metric per cost_type."""
        tag_values_kwargs = [{"value": 0.2}]
        cost_model = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
            "markup": {"value": 10, "unit": "percent"},
            "rates": [
                {"metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR}},
                {"metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR}},
            ],
        }
        cost_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        cost_model["rates"][1]["tag_rates"] = format_tag_rate(tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=cost_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = str(serializer.errors["rates"])
        expected_sub_string = "Duplicate tag_key"
        self.assertIn(expected_sub_string, result_err_msg)

    def test_tag_rates_on_duplicate_metric_per_cost_type(self):
        """Test that specifying both tiered and tag rates fails."""
        tag_values_kwargs = [{"value": 0.2}]
        cost_model = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": Provider.PROVIDER_OCP,
            "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
            "markup": {"value": 10, "unit": "percent"},
            "rates": [
                {"metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR}},
                {"metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR}},
            ],
            "currency": "USD",
        }
        cost_model["rates"][0]["tag_rates"] = format_tag_rate(tag_key="k1", tag_values=tag_values_kwargs)
        cost_model["rates"][1]["tag_rates"] = format_tag_rate(tag_key="k2", tag_values=tag_values_kwargs)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=cost_model, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            serializer.save()
            serializer.data

    def test_rate_to_representation(self):
        """
        Test the tag rate value is converted to decimal.
        """
        rates = {
            "tiered_rates": self.ocp_data["rates"][0],
            "tag_rates": {
                "metric": {"name": metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR},
                "tag_rates": format_tag_rate(tag_values=[{"value": 1}]),
            },
        }
        for key, rate in rates.items():
            with tenant_context(self.tenant):
                serializer = RateSerializer(data=rate)
                RateSerializer._convert_to_decimal(rate)
                serializer.to_representation(rate)
            rate_info = rate.get(key)
            if isinstance(rate_info, dict):
                values = rate_info.get("tag_values")
            else:
                values = rate_info
            for value in values:
                self.assertIsInstance(value["value"], Decimal)

    def test_error_on_duplicate_tag_values(self):
        """Test that specifying both tiered and tag rates fails."""
        tag_value = {"tag_value": "key_one", "value": 0.2}
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=[tag_value, tag_value])
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))
        result_err_msg = str(serializer.errors["rates"])
        expected_sub_string = "Duplicate tag_value"
        self.assertIn(expected_sub_string, result_err_msg)

    def test_validate_source_uuid_error(self):
        """Test validate source uuid error."""
        tag_value = {"tag_value": "key_one", "value": 0.2}
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=[tag_value])
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                serializer.validate_source_uuids([uuid4()])

    def test_distribution_choices_added_successfully(self):
        """Test that source distribution is a valid choice and added successsfully."""
        valid_choices = ["cpu", "memory"]
        for good_input in valid_choices:
            self.ocp_data["distribution"] = good_input
            self.assertEqual(self.ocp_data["distribution"], good_input)
            with tenant_context(self.tenant):
                serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
                self.assertTrue(serializer.is_valid(raise_exception=True))
                instance = serializer.save()
                self.assertIsNotNone(instance)
                self.assertIsNotNone(instance.uuid)
                self.assertEqual(instance.distribution, good_input)

    def test_error_bad_distribution_choice(self):
        """Test that source successfully fails if bad distribution type."""
        bad_choice_list = ["bad1", "bad2", "bad3"]
        for bad_input in bad_choice_list:
            self.ocp_data["distribution"] = bad_input
            self.assertEqual(self.ocp_data["distribution"], bad_input)
            with tenant_context(self.tenant):
                serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
                with self.assertRaises(serializers.ValidationError):
                    serializer.validate_distribution(bad_input)

    def test_defaulting_currency(self):
        """Test if currency is none it defaults using get_currency method."""
        ocp_metric = metric_constants.OCP_METRIC_CPU_CORE_USAGE_HOUR
        ocp_source_type = Provider.PROVIDER_OCP
        tiered_rates = [{"unit": "USD", "value": 0.22}]
        ocp_data = {
            "name": "Test Cost Model",
            "description": "Test",
            "source_type": ocp_source_type,
            "providers": [{"uuid": self.provider.uuid, "name": self.provider.name}],
            "markup": {"value": 10, "unit": "percent"},
            "rates": [{"metric": {"name": ocp_metric}, "tiered_rates": tiered_rates}],
        }
        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=ocp_data, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertEqual(instance.currency, get_currency(self.request_context["request"]))

    def test_cost_model_currency(self):
        """Test if currency is set in cost model."""
        self.ocp_data["currency"] = "AUD"
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {
                "unit": "AUD",
                "value": 0.22,
                "usage": {"usage_start": None, "usage_end": None},
                "cost_type": "Infrastructure",
            }
        ]
        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

        self.assertEqual(instance.currency, "AUD")

    def test_invalid_currency(self):
        """Test failure while handling invalid cost_type."""
        self.ocp_data["currency"] = "invalid"
        serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_tiered_not_matching_currency(self):
        """Test if tiered rates do not match currency raises a validation error."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {
                "unit": "JPY",
                "value": 0.22,
                "usage": {"usage_start": None, "usage_end": None},
                "cost_type": "Infrastructure",
            }
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))

        self.ocp_data["rates"][0]["tiered_rates"] = format_tag_rate(
            [
                {
                    "unit": "USD",
                    "value": 0.22,
                    "usage": {"usage_start": None, "usage_end": None, "unit": "JPY"},
                    "cost_type": "Infrastructure",
                }
            ]
        )

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))

    def test_tagged_not_matching_currency(self):
        """Test if tagged rates do not match currency raises a validation error."""
        tag_value = {"tag_value": "key_one", "value": 0.2, "unit": "JPY"}
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=[tag_value])

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            with self.assertRaises(serializers.ValidationError):
                self.assertFalse(serializer.is_valid(raise_exception=True))

    def test_valid_tiered_matching_currency(self):
        """Test if tiered rates do not match currency raises a validation error."""
        self.ocp_data["rates"][0]["tiered_rates"] = [
            {
                "unit": "USD",
                "value": 0.22,
                "usage": {"usage_start": None, "usage_end": None},
                "cost_type": "Infrastructure",
            }
        ]
        self.ocp_data["currency"] = "USD"

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))

        self.ocp_data["rates"][0]["tiered_rates"] = [
            {
                "unit": "USD",
                "value": 0.22,
                "usage": {"usage_start": None, "usage_end": None, "unit": "USD"},
                "cost_type": "Infrastructure",
            }
        ]

        self.ocp_data["currency"] = "USD"

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_valid_tagged_matching_currency(self):
        tag_value = {"tag_value": "key_one", "value": 0.2, "unit": "USD"}
        self.basic_model["rates"][0]["tag_rates"] = format_tag_rate(tag_values=[tag_value])

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.basic_model, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_valid_distribution_info_keys(self):
        """Test that source distribution_info object has valid keys."""

        valid_distrib_obj = {"distribution_type": "cpu", "worker_cost": True, "platform_cost": True}
        self.ocp_data["distribution_info"] = valid_distrib_obj
        self.assertEqual(self.ocp_data["distribution_info"], valid_distrib_obj)
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            instance = serializer.save()
            self.assertIsNotNone(instance)
            # Add in default options
            valid_distrib_obj[metric_constants.NETWORK_UNATTRIBUTED] = False
            valid_distrib_obj[metric_constants.STORAGE_UNATTRIBUTED] = False
            self.assertEqual(instance.distribution_info, valid_distrib_obj)

    def test_invalid_distribution_info_keys(self):
        """Test that source distribution_info object has invalid keys."""
        bad_key1 = "bad_key"
        bad_key2 = "worst_key"
        invalid_distrib_info_keys = {bad_key1: "", bad_key2: True, "worker_cost": False}
        with tenant_context(self.tenant):
            serializer = DistributionSerializer(data=invalid_distrib_info_keys)
            self.assertFalse(serializer.is_valid(raise_exception=False))
            self.assertNotIn(bad_key1, serializer.data)
            self.assertNotIn(bad_key2, serializer.data)

    def test_none_distribution_info_returns_defaults(self):
        """Test that a none distribution_info object uses default options."""
        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            instance = serializer.save()
            self.assertIsNotNone(instance)
            self.assertEqual(instance.distribution_info, DEFAULT_DISTRIBUTION_INFO)

    def test_empty_distribution_info_returns_defaults(self):
        """Test that an empty distribution_info object returns default options."""
        self.ocp_data["distribution_info"] = {}
        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
            self.assertTrue(serializer.is_valid(raise_exception=True))
            instance = serializer.save()
            self.assertEqual(instance.distribution_info, DEFAULT_DISTRIBUTION_INFO)

    def test_all_valid_distribution_info_permutations(self):
        """Completely overkill test for all valid permutations of distribution_info keys and values."""
        # Define the keys and their possible values
        valid_values = {
            "distribution_type": ["cpu", "memory"],
            "worker_cost": [True, False],
            "platform_cost": [True, False],
            "network_unattributed": [True, False],
            "storage_unattributed": [True, False],
        }

        # Generate all combinations of key-value pairs
        table = []
        for r in range(1, len(valid_values) + 1):
            for subset in combinations(valid_values.keys(), r):
                subset_values = {p: valid_values[p] for p in subset}
                table.extend(
                    dict(zip(subset_values.keys(), combination)) for combination in product(*subset_values.values())
                )
        for test_case in table:
            with self.subTest(distribution_info=test_case):
                self.ocp_data["distribution_info"] = test_case
                with tenant_context(self.tenant):
                    serializer = CostModelSerializer(data=self.ocp_data, context=self.request_context)
                    self.assertTrue(serializer.is_valid(raise_exception=True))
                    instance = serializer.save()
                    self.assertIsNotNone(instance)
                    expected_distrib_obj = {**DEFAULT_DISTRIBUTION_INFO, **test_case}
                    self.assertEqual(instance.distribution_info, expected_distrib_obj)
