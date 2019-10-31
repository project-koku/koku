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

import random
from decimal import Decimal

import faker
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.metrics.models import CostModelMetricsMap
from api.metrics.serializers import SOURCE_TYPE_MAP
from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from cost_models.models import CostModel, CostModelMap
from cost_models.serializers import CostModelSerializer, UUIDKeyRelatedField


class CostModelSerializerTest(IamTestCase):
    """Cost Model serializer tests."""

    fake = faker.Faker()

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        request = self.request_context['request']
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            request.user = user

        provider_data = {
            'name': 'test_provider',
            'type': Provider.PROVIDER_OCP,
            'authentication': {'provider_resource_name': self.fake.word()},
        }
        serializer = ProviderSerializer(
            data=provider_data, context=self.request_context
        )
        if serializer.is_valid(raise_exception=True):
            self.provider = serializer.save()

        ocp_metric = CostModelMetricsMap.OCP_METRIC_CPU_CORE_USAGE_HOUR
        ocp_source_type = 'OCP'
        tiered_rates = [{'unit': 'USD', 'value': 0.22}]
        self.ocp_data = {
            'name': 'Test Cost Model',
            'description': 'Test',
            'source_type': ocp_source_type,
            'providers': [{'uuid': self.provider.uuid, 'name': self.provider.name}],
            'markup': {'value': 10, 'unit': 'percent'},
            'rates': [{'metric': {'name': ocp_metric}, 'tiered_rates': tiered_rates}],
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
        uuid_field = UUIDKeyRelatedField(
            queryset=Provider.objects.all(), pk_field='uuid'
        )
        self.assertFalse(uuid_field.use_pk_only_optimization())
        self.assertEqual(
            self.provider.uuid, uuid_field.to_internal_value(self.provider.uuid)
        )
        self.assertEqual(
            self.provider.uuid, uuid_field.to_representation(self.provider)
        )
        self.assertEqual(self.provider.uuid, uuid_field.display_value(self.provider))

    def test_error_on_invalid_provider(self):
        """Test error with an invalid provider id."""
        self.ocp_data.update(
            {'provider_uuids': ['1dd7204c-72c4-4ec4-95bc-d5c447688b27']}
        )
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_not_OCP_source_type_with_markup(self):
        """Test that a source type is valid if it has markup."""
        self.ocp_data['source_type'] = 'AWS'
        self.ocp_data['rates'] = []

        with tenant_context(self.tenant):
            instance = None
            serializer = CostModelSerializer(data=self.ocp_data)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
            self.assertIsNotNone(instance)
            self.assertIsNotNone(instance.markup)

    def test_error_source_type_with_markup(self):
        """Test that non-existent source type is invalid."""
        self.ocp_data['source_type'] = 'invalid-source'

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_source_type_without_markup(self):
        """Test error when non OCP source is added without markup."""
        self.ocp_data['source_type'] = 'AWS'
        self.ocp_data['markup'] = {}
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_nonOCP_source_type_with_markup_and_rates(self):
        """Test error when non OCP source is added with markup and rates."""
        self.ocp_data['source_type'] = 'AWS'

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_invalid_metric(self):
        """Test error on an invalid metric rate."""
        self.ocp_data.get('rates', [])[0]['metric']['name'] = 'invalid_metric'
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_usage_bad_start_bound(self):
        """Test error on a usage_start that does not cover lower bound."""
        self.ocp_data['rates'][0]['tiered_rates'][0]['usage'] = {
            'usage_start': 5,
            'usage_end': None,
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_usage_bad_upper_bound(self):
        """Test error on a usage_end that does not cover lower bound."""
        self.ocp_data['rates'][0]['tiered_rates'][0]['usage'] = {
            'usage_start': None,
            'usage_end': 5,
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_rate_type(self):
        """Test error when trying to create an invalid rate input."""
        self.ocp_data['rates'][0].pop('tiered_rates')
        self.ocp_data['rates'][0]['bad_rates'] = []
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_negative_rate(self):
        """Test error when trying to create an negative rate input."""
        self.ocp_data['rates'][0]['tiered_rates'][0]['value'] = float(
            round(Decimal(random.random()), 6) * -1
        )

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_no_rate(self):
        """Test error when trying to create an empty rate."""
        self.ocp_data['rates'][0]['tiered_rates'] = []

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_usage_start(self):
        """Test error when trying to create a negative tiered usage_start."""
        self.ocp_data['rates'][0]['tiered_rates'][0]['usage'] = {
            'usage_start': float(round(Decimal(random.random()), 6) * -1),
            'usage_end': 20.0,
        }
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_usage_end(self):
        """Test error when trying to create a negative tiered usage_end."""
        self.ocp_data['rates'][0]['tiered_rates'][0]['usage'] = {
            'usage_start': 10.0,
            'usage_end': float(round(Decimal(random.random()), 6) * -1),
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_tier_usage_end_less_than(self):
        """Test error when trying to create a tiered usage_end less than usage_start."""
        self.ocp_data['rates'][0]['tiered_rates'][0]['usage'] = {
            'usage_start': 10.0,
            'usage_end': 3.0,
        }

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_create_cpu_core_per_hour_tiered_rate(self):
        """Test creating a cpu_core_per_hour rate."""
        self.ocp_data['rates'][0]['tiered_rates'] = [
            {
                'unit': 'USD',
                'value': 0.22,
                'usage': {'usage_start': None, 'usage_end': 10.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 10.0, 'usage_end': None},
            },
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
        self.ocp_data['rates'][0]['tiered_rates'] = [
            {
                'unit': 'USD',
                'value': 0.22,
                'usage': {'usage_start': 0.0, 'usage_end': 7.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 10.0, 'usage_end': 20.0},
            },
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_tiered_rate_with_gaps(self):
        """Test creating a tiered rate with a gap between the tiers."""
        self.ocp_data['rates'][0]['tiered_rates'] = [
            {
                'unit': 'USD',
                'value': 0.22,
                'usage': {'usage_start': None, 'usage_end': 7.0},
            },
            {'unit': 'USD', 'value': 0.26, 'usage_start': 10.0, 'usage_end': None},
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_create_storage_tiered_rate(self):
        """Test creating a storage tiered rate."""
        storage_rates = (
            CostModelMetricsMap.OCP_METRIC_STORAGE_GB_REQUEST_MONTH,
            CostModelMetricsMap.OCP_METRIC_STORAGE_GB_USAGE_MONTH,
        )
        for storage_rate in storage_rates:
            ocp_data = {
                'name': 'Test Cost Model',
                'description': 'Test',
                'source_type': 'OCP',
                'providers': [{'uuid': self.provider.uuid, 'name': self.provider.name}],
                'rates': [
                    {
                        'metric': {'name': storage_rate},
                        'tiered_rates': [
                            {
                                'unit': 'USD',
                                'value': 0.22,
                                'usage': {'usage_start': None, 'usage_end': 10.0},
                            },
                            {
                                'unit': 'USD',
                                'value': 0.26,
                                'usage': {'usage_start': 10.0, 'usage_end': None},
                            },
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
            CostModelMetricsMap.OCP_METRIC_STORAGE_GB_REQUEST_MONTH,
            CostModelMetricsMap.OCP_METRIC_STORAGE_GB_USAGE_MONTH,
        )
        for storage_rate in storage_rates:
            ocp_data = {
                'name': 'Test Cost Model',
                'description': 'Test',
                'source_type': 'OCP',
                'providers': [{'uuid': self.provider.uuid, 'name': self.provider.name}],
                'rates': [
                    {
                        'metric': {'name': storage_rate},
                        'tiered_rates': [{'unit': 'USD', 'value': 0.22}],
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

    def test_tiered_rate_with_overlaps(self):
        """Test creating a tiered rate with a overlaps between the tiers."""
        self.ocp_data['rates'][0]['tiered_rates'] = [
            {
                'unit': 'USD',
                'value': 0.22,
                'usage': {'usage_start': None, 'usage_end': 10.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 5.0, 'usage_end': 20.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 20.0, 'usage_end': None},
            },
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_tiered_rate_with_duplicate(self):
        """Test creating a tiered rate with duplicate tiers."""
        self.ocp_data['rates'][0]['tiered_rates'] = [
            {
                'unit': 'USD',
                'value': 0.22,
                'usage': {'usage_start': None, 'usage_end': 10.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 10.0, 'usage_end': 20.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 10.0, 'usage_end': 20.0},
            },
            {
                'unit': 'USD',
                'value': 0.26,
                'usage': {'usage_start': 20.0, 'usage_end': None},
            },
        ]

        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_get_metric_display_data_openshift(self):
        """Test the display data helper function for OpenShift metrics."""
        serializer = CostModelSerializer(data=None)

        for metric_choice in CostModelMetricsMap.METRIC_CHOICES:
            response = serializer._get_metric_display_data('OCP', metric_choice[0])
            self.assertIsNotNone(response.label_measurement_unit)
            self.assertIsNotNone(response.label_measurement)
            self.assertIsNotNone(response.label_metric)

    def test_check_for_duplicate_metrics(self):
        """Check that duplicate rate types for a metric are rejected."""
        rate = self.ocp_data['rates'][0]
        # Add another tiered rate entry for the same metric
        self.ocp_data['rates'].append(rate)
        # Make sure we don't allow two tiered rate entries in rates
        # for the same metric
        with tenant_context(self.tenant):
            serializer = CostModelSerializer(data=self.ocp_data)
            with self.assertRaises(serializers.ValidationError):
                serializer._check_for_duplicate_metrics(self.ocp_data['rates'])
