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
"""Test the Rate serializers."""

import random
from decimal import Decimal

import faker
from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.serializers import ProviderSerializer
from rates.models import Rate
from rates.serializers import RateSerializer, UUIDKeyRelatedField


class RateSerializerTest(IamTestCase):
    """Rate serializer tests."""

    fake = faker.Faker()

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        request = self.request_context['request']
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            user = serializer.save()
            request.user = user

        provider_data = {'name': 'test_provider',
                         'type': Provider.PROVIDER_OCP,
                         'authentication': {
                             'provider_resource_name': self.fake.word()
                         }}
        serializer = ProviderSerializer(data=provider_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            self.provider = serializer.save()

    def test_uuid_key_related_field(self):
        """Test the uuid key related field."""
        uuid_field = UUIDKeyRelatedField(queryset=Provider.objects.all(), pk_field='uuid')
        self.assertFalse(uuid_field.use_pk_only_optimization())
        self.assertEqual(self.provider.uuid,
                         uuid_field.to_internal_value(self.provider.uuid))
        self.assertEqual(self.provider.uuid,
                         uuid_field.to_representation(self.provider))
        self.assertEqual(self.provider.uuid,
                         uuid_field.display_value(self.provider))

    def test_error_on_invalid_provider(self):
        """Test error with an invalid provider id."""
        rate = {'provider_uuid': '1dd7204c-72c4-4ec4-95bc-d5c447688b27',
                'metric': Rate.METRIC_MEM_GB_HOUR,
                'tiered_rate': [{
                    'value': round(Decimal(random.random()), 6),
                    'unit': 'USD',
                    'usage_start': None,
                    'usage_end': None
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_invalid_metric(self):
        """Test error on an invalid metric rate."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': 'invalid_metric',
                'tiered_rate': [{
                    'value': round(Decimal(random.random()), 6),
                    'unit': 'USD',
                    'usage_start': None,
                    'usage_end': None
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_rate_type(self):
        """Test error when trying to create an invalid rate input."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'invalid_rate': {
                    'value': round(Decimal(random.random()), 6),
                    'unit': 'USD'
                }
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_on_negative_rate(self):
        """Test error when trying to create an negative rate input."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'value': (round(Decimal(random.random()), 6) * -1),
                    'unit': 'USD',
                    'usage_start': None,
                    'usage_end': None
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_no_rate(self):
        """Test error when trying to create an empty rate."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_value(self):
        """Test error when trying to create a negative tiered value."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': (round(Decimal(random.random()), 6) * -1),
                    'usage_start': 10.0,
                    'usage_end': 20.0
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_usage_start(self):
        """Test error when trying to create a negative tiered usage_start."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': 1.0,
                    'usage_start': (round(Decimal(random.random()), 6) * -1),
                    'usage_end': 20.0
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_neg_tier_usage_end(self):
        """Test error when trying to create a negative tiered usage_end."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': 1.0,
                    'usage_start': 10.0,
                    'usage_end': (round(Decimal(random.random()), 6) * -1)
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_error_tier_usage_end_less_than(self):
        """Test error when trying to create a tiered usage_end less than usage_start."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': 1.0,
                    'usage_start': 10.0,
                    'usage_end': 3.0
                }]
                }
        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_create_cpu_core_per_hour_tiered_rate(self):
        """Test creating a cpu_core_per_hour rate."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': 0.22,
                    'usage_start': None,
                    'usage_end': 10.0
                }, {
                    'unit': 'USD',
                    'value': 0.26,
                    'usage_start': 10.0,
                    'usage_end': None
                }]
                }

        with tenant_context(self.tenant):
            instance = None
            serializer = RateSerializer(data=rate)
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()

            self.assertIsNotNone(instance)
            self.assertIsNotNone(instance.uuid)

    def test_tiered_rate_null_start_end(self):
        """Test creating a rate with out a start and end."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': 0.22,
                    'usage_start': 0.0,
                    'usage_end': 7.0
                }, {
                    'unit': 'USD',
                    'value': 0.26,
                    'usage_start': 10.0,
                    'usage_end': 20.0
                }]
                }

        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_tiered_rate_with_gaps(self):
        """Test creating a tiered rate with a gap between the tiers."""
        rate = {'provider_uuid': self.provider.uuid,
                'metric': Rate.METRIC_CPU_CORE_HOUR,
                'tiered_rate': [{
                    'unit': 'USD',
                    'value': 0.22,
                    'usage_start': None,
                    'usage_end': 7.0
                }, {
                    'unit': 'USD',
                    'value': 0.26,
                    'usage_start': 10.0,
                    'usage_end': None
                }]
                }

        with tenant_context(self.tenant):
            serializer = RateSerializer(data=rate)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()
