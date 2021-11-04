#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Serializers."""
import datetime

from rest_framework import serializers
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from masu.api.sourceproviders.providers.serializers import ProviderSerializer


class ProviderserializerTest(IamTestCase):
    """Provider serializer tests"""

    def setUp(self):
        super().setUp()
        self.provider = Provider.objects.first()
        self.serializer = ProviderSerializer(self.provider)
        self.basic_model = {
            "uuid": Provider.objects.first().uuid,
            "name": "Test Provider Source",
            "type": "Provider Local",
            "setup_complete": True,
            "created_timestamp": datetime.datetime.now(),
            "data_updated_timestamp": datetime.datetime.now(),
            "active": True,
            "authentication_id": 1,
            "billing_source_id": 1,
            "created_by_id": 1,
            "customer_id": 1,
            "infrastructure_id": 1,
            "paused": False,
        }

    def test_provider_contains_expected_fields(self):
        """Tests ProviderSerializer is utilizing expected fields"""
        data = self.serializer.data
        self.assertEqual(
            set(data.keys()),
            {
                "uuid",
                "name",
                "type",
                "setup_complete",
                "created_timestamp",
                "data_updated_timestamp",
                "active",
                "authentication_id",
                "billing_source_id",
                "created_by_id",
                "customer_id",
                "infrastructure_id",
                "paused",
            },
        )

    def test_valid_data(self):
        """Tests ManifestSerializer with all valid data."""
        with tenant_context(self.tenant):
            serializer = ProviderSerializer(data=self.basic_model)
            self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_invalid_string_data(self):
        """Tests ManifestSerializer invalid string."""
        self.basic_model["uuid"] = 1
        serializer = ProviderSerializer(data=self.basic_model)
        self.assertRaises(TypeError, serializer.is_valid(raise_exception=True))

    def test_invalid_date_data(self):
        """Tests ManifestSerializer invalid date."""
        self.basic_model["created_timestamp"] = "invalid date"
        with tenant_context(self.tenant):
            serializer = ProviderSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_invalid_boolean_data(self):
        """Tests ManifestSerializer invalid boolean."""
        self.basic_model["paused"] = 27
        with tenant_context(self.tenant):
            serializer = ProviderSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()
