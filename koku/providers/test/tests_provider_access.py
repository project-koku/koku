#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the ProviderAccessor implementation for the Koku consumption."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.serializers import ValidationError

from api.models import Provider
from providers.aws.provider import AWSProvider
from providers.aws_local.provider import AWSLocalProvider
from providers.azure.provider import AzureProvider
from providers.azure_local.provider import AzureLocalProvider
from providers.ocp.provider import OCPProvider
from providers.provider_access import ProviderAccessor
from providers.provider_access import ProviderAccessorError


class ProviderAccessorTestCase(TestCase):
    """Parent Class for ProviderAccessor test cases."""

    def setup(self):
        """Create test case objects."""
        pass

    def tearDown(self):
        """Tear down test case objects."""
        pass

    def test_establish_aws_provider(self):
        """Verify that an aws service is created."""
        provider_name = Provider.PROVIDER_AWS
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)

    def test_establish_ocp_provider(self):
        """Verify that an ocp service is created."""
        provider_name = Provider.PROVIDER_OCP
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)

    def test_establish_aws_local_provider(self):
        """Verify that AWS local provider is created."""
        provider_name = Provider.PROVIDER_AWS_LOCAL
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, AWSLocalProvider))

    def test_establish_azure_provider(self):
        """Verify that AZURE provider is created."""
        provider_name = Provider.PROVIDER_AZURE
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, AzureProvider))

    def test_establish_azure_local_provider(self):
        """Verify that AZURE local provider is created."""
        provider_name = Provider.PROVIDER_AZURE_LOCAL
        interface = ProviderAccessor(provider_name)
        self.assertIsNotNone(interface.service)
        self.assertTrue(isinstance(interface.service, AzureLocalProvider))

    def test_establish_invalid_provider(self):
        """Verify that an invalid service is created."""
        provider_name = "BAD"
        interface = ProviderAccessor(provider_name)
        self.assertIsNone(interface.service)

    def test_get_name_aws(self):
        """Get name of aws service provider."""
        provider = AWSProvider()
        interface = ProviderAccessor(provider.name())
        self.assertEqual(provider.name(), interface.service_name())

    def test_get_name_ocp(self):
        """Get name of ocp service provider."""
        provider = OCPProvider()
        interface = ProviderAccessor(provider.name())
        self.assertEqual(provider.name(), interface.service_name())

    def test_usage_source_ready(self):
        """Get status of cost usage source."""
        provider = Provider.PROVIDER_AWS
        interface = ProviderAccessor(provider)

        credential = "arn:aws:s3:::my_s3_bucket"
        source_name = "my_s3_bucket"

        source_ready = False
        with patch.object(AWSProvider, "cost_usage_source_is_reachable", return_value=True):
            source_ready = interface.cost_usage_source_ready(credential, source_name)
        self.assertTrue(source_ready)

    def test_get_infrastructure_type_exception(self):
        """Get infrastructure type with exception."""
        provider = OCPProvider()
        interface = ProviderAccessor(provider.name())
        with self.assertRaises(ProviderAccessorError):
            with patch.object(OCPProvider, "infra_type_implementation", side_effect=Exception("test")):
                interface.infrastructure_type(None, None)

    def test_get_infrastructure_key_list_exception(self):
        """Get infrastructure key list with exception."""
        provider = OCPProvider()
        interface = ProviderAccessor(provider.name())
        with self.assertRaises(ProviderAccessorError):
            with patch.object(OCPProvider, "infra_key_list_implementation", side_effect=Exception("test")):
                interface.infrastructure_type(None, None)

    def test_invalid_provider_funcs(self):
        """Verify that an invalid service is created and raises errors."""
        provider_name = "BAD"
        interface = ProviderAccessor(provider_name)
        self.assertIsNone(interface.service)

        with self.assertRaises(ValidationError):
            interface.cost_usage_source_ready({}, {})

        with self.assertRaises(ValidationError):
            interface.service_name()

        with self.assertRaises(ValidationError):
            interface.infrastructure_type({}, {})

        with self.assertRaises(ValidationError):
            interface.infrastructure_key_list({}, {})
