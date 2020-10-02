#
# Copyright 2019 Red Hat, Inc.
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
"""Test the Kafka Source Manager."""
import logging
from unittest.mock import patch

from django.test import TestCase
from faker import Faker
from rest_framework.exceptions import ValidationError

from api.iam.models import Tenant
from api.models import Provider
from api.provider.provider_builder import ProviderBuilder
from api.provider.provider_builder import ProviderBuilderError
from koku.middleware import IdentityHeaderMiddleware
from providers.provider_access import ProviderAccessor
from sources.config import Config

faker = Faker()


class MockSourceObject:
    def __init__(self, name, type, authentication, billing_source, uuid=None):
        self.name = name
        self.source_type = type
        self.authentication = authentication
        self.billing_source = billing_source
        self.source_uuid = uuid
        self.koku_uuid = uuid


class ProviderBuilderTest(TestCase):
    """Test cases for ProviderBuilder."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        account = "12345"
        IdentityHeaderMiddleware.create_customer(account)

    def setUp(self):
        """Test case setup."""
        super().setUp()
        self.name = "Test Provider"
        self.provider_type = Provider.PROVIDER_AWS
        self.authentication = {"credentials": {"role_arn": "testauth"}}
        self.billing_source = {"data_source": {"bucket": "testbillingsource"}}
        self.source_uuid = faker.uuid4()
        self.mock_source = MockSourceObject(
            self.name, self.provider_type, self.authentication, self.billing_source, self.source_uuid
        )

    def test_create_provider(self):
        """Test to create a provider."""
        # Delete tenants
        Tenant.objects.all().delete()
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            mock_source = MockSourceObject(self.name, self.provider_type, self.authentication, self.billing_source)
            provider = client.create_provider_from_source(mock_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_no_tenant(self):
        """Test to create a provider after tenant was removed."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            mock_source = MockSourceObject(self.name, self.provider_type, self.authentication, self.billing_source)
            provider = client.create_provider_from_source(mock_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_with_source_uuid(self):
        """Test to create a provider with source uuid ."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), self.source_uuid)

    def test_create_provider_exceptions(self):
        """Test to create a provider with a non-recoverable error."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with self.assertRaises(ValidationError):
            client.create_provider_from_source(self.mock_source)

    def test_destroy_provider(self):
        """Test to destroy a provider."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), self.source_uuid)
            client.destroy_provider(self.source_uuid)
            with self.assertRaises(Provider.DoesNotExist):
                Provider.objects.get(uuid=self.source_uuid)

    def test_destroy_provider_exception(self):
        """Test to destroy a provider with a connection error."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), self.source_uuid)
            logging.disable(logging.NOTSET)
            with self.assertLogs(logger="api.provider.provider_builder", level=logging.INFO):
                client.destroy_provider(faker.uuid4())

    def test_update_provider(self):
        """Test to update a provider."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            new_name = "Aws Test"
            self.mock_source.name = new_name
            updated_provider = client.update_provider_from_source(self.mock_source)
            self.assertEqual(updated_provider.uuid, provider.uuid)
            self.assertEqual(updated_provider.name, new_name)

    def test_update_provider_exception(self):
        """Test to update a provider with a connection error."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with self.assertRaises(Provider.DoesNotExist):
            client.update_provider_from_source(self.mock_source)

    def test_update_provider_error(self):
        """Test to update a provider with a koku server error."""
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            client.create_provider_from_source(self.mock_source)
        with self.assertRaises(ValidationError):
            new_name = "Aws Test"
            self.mock_source.name = new_name
            client.update_provider_from_source(self.mock_source)

    def test__build_credentials_auth(self):
        """Test to build Koku Provider authentication json obj."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "authentication": {"credentials": {"role_arn": "arn:fake"}},
                "expected_response": {"credentials": {"role_arn": "arn:fake"}},
            },
            {
                "provider_type": Provider.PROVIDER_OCP,
                "authentication": {"credentials": {"role_arn": "test-cluster-id"}},
                "expected_response": {"credentials": {"role_arn": "test-cluster-id"}},
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "authentication": {"credentials": {"foo": "bar"}},
                "expected_response": {"credentials": {"foo": "bar"}},
            },
        ]
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            with self.subTest(test=test):
                response = client._build_credentials_auth(test.get("authentication"))
                self.assertEqual(response, test.get("expected_response"))

    def test__build_credentials_auth_errors(self):
        """Test to build Koku Provider authentication json obj with errors."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "authentication": {"credentialz": {"role_arn": "arn:fake"}},
                "expected_response": ProviderBuilderError,
            },
            {
                "provider_type": Provider.PROVIDER_OCP,
                "authentication": {"credentialz": "test-cluster-id"},
                "expected_response": ProviderBuilderError,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "authentication": {"credentialz": {"foo": "bar"}},
                "expected_response": ProviderBuilderError,
            },
        ]
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            with self.assertRaises(test.get("expected_response")):
                client._build_credentials_auth(test.get("authentication"))

    def test_get_billing_source_for_provider(self):
        """Test to build Koku Provider billing_source json obj."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "billing_source": {"data_source": {"bucket": "test-bucket"}},
                "expected_response": {"data_source": {"bucket": "test-bucket"}},
            },
            {"provider_type": Provider.PROVIDER_OCP, "billing_source": {}, "expected_response": {}},
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"foo": "bar"}},
                "expected_response": {"data_source": {"foo": "bar"}},
            },
        ]
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            with self.subTest(test=test):
                response = client.get_billing_source_for_provider(
                    test.get("provider_type"), test.get("billing_source")
                )
                self.assertEqual(response, test.get("expected_response"))

    def test_get_billing_source_for_provider_error(self):
        """Test to build Koku Provider billing_source json obj with errors."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "billing_source": {"data_source": "test-bucket"},
                "expected_response": ProviderBuilderError,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"bucket": {"foo": "bar"}},
                "expected_response": ProviderBuilderError,
            },
        ]
        client = ProviderBuilder(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            with self.assertRaises(test.get("expected_response")):
                client.get_billing_source_for_provider(test.get("provider_type"), test.get("billing_source"))
