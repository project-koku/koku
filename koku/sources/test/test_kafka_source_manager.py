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

from api.models import Provider
from koku.middleware import IdentityHeaderMiddleware
from providers.provider_access import ProviderAccessor
from sources.config import Config
from sources.kafka_source_manager import KafkaSourceManager
from sources.kafka_source_manager import KafkaSourceManagerError

faker = Faker()


class KafkaSourceManagerTest(TestCase):
    """Test cases for KafkaSourceManager."""

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
        self.authentication = {"resource_name": "testauth"}
        self.billing_source = {"bucket": "testbillingsource"}

    def test_create_provider(self):
        """Test to create a provider."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider(self.name, self.provider_type, self.authentication, self.billing_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_with_source_uuid(self):
        """Test to create a provider with source uuid ."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        source_uuid = faker.uuid4()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider(
                self.name, self.provider_type, self.authentication, self.billing_source, source_uuid
            )
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), source_uuid)

    def test_create_provider_exceptions(self):
        """Test to create a provider with a non-recoverable error."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        with self.assertRaises(ValidationError):
            source_uuid = faker.uuid4()
            client.create_provider(
                self.name, self.provider_type, self.authentication, self.billing_source, source_uuid
            )

    @patch("masu.processor.tasks.refresh_materialized_views.delay")
    def test_destroy_provider(self, mock_views):
        """Test to destroy a provider."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)

        source_uuid = faker.uuid4()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider(
                self.name, self.provider_type, self.authentication, self.billing_source, source_uuid
            )
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), source_uuid)
            client.destroy_provider(source_uuid)
            with self.assertRaises(Provider.DoesNotExist):
                Provider.objects.get(uuid=source_uuid)

    def test_destroy_provider_exception(self):
        """Test to destroy a provider with a connection error."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        source_uuid = faker.uuid4()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider(
                self.name, self.provider_type, self.authentication, self.billing_source, source_uuid
            )
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), source_uuid)
            logging.disable(logging.NOTSET)
            with self.assertLogs(logger="sources.kafka_source_manager", level=logging.INFO):
                client.destroy_provider(faker.uuid4())

    def test_update_provider(self):
        """Test to update a provider."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        source_uuid = faker.uuid4()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider(
                self.name, self.provider_type, self.authentication, self.billing_source, source_uuid
            )
            new_name = "Aws Test"
            updated_provider = client.update_provider(
                source_uuid, new_name, Provider.PROVIDER_AWS, {"resource_name": "arn:test"}, {"bucket": "bucket"}
            )
            self.assertEqual(updated_provider.uuid, provider.uuid)
            self.assertEqual(updated_provider.name, new_name)

    def test_update_provider_exception(self):
        """Test to update a provider with a connection error."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        expected_uuid = faker.uuid4()
        with self.assertRaises(Provider.DoesNotExist):
            client.update_provider(
                expected_uuid, "Aws Test", Provider.PROVIDER_AWS, {"resource_name": "arn:test"}, {"bucket": "bucket"}
            )

    def test_update_provider_error(self):
        """Test to update a provider with a koku server error."""
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)
        source_uuid = faker.uuid4()
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            client.create_provider(
                self.name, self.provider_type, self.authentication, self.billing_source, source_uuid
            )
        with self.assertRaises(ValidationError):
            client.update_provider(
                source_uuid, "Aws Test", Provider.PROVIDER_AWS, {"resource_name": "arn:test"}, {"bucket": "bucket"}
            )

    def test_get_authentication_for_provider(self):
        """Test to build Koku Provider authentication json obj."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "authentication": {"resource_name": "arn:fake"},
                "expected_response": {"provider_resource_name": "arn:fake"},
            },
            {
                "provider_type": Provider.PROVIDER_OCP,
                "authentication": {"resource_name": "test-cluster-id"},
                "expected_response": {"provider_resource_name": "test-cluster-id"},
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "authentication": {"credentials": {"foo": "bar"}},
                "expected_response": {"credentials": {"foo": "bar"}},
            },
        ]
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            response = client.get_authentication_for_provider(test.get("provider_type"), test.get("authentication"))
            self.assertEqual(response, test.get("expected_response"))

    def test_get_authentication_for_provider_errors(self):
        """Test to build Koku Provider authentication json obj with errors."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "authentication": {"resource_namez": "arn:fake"},
                "expected_response": KafkaSourceManagerError,
            },
            {
                "provider_type": Provider.PROVIDER_OCP,
                "authentication": {"resource_namez": "test-cluster-id"},
                "expected_response": KafkaSourceManagerError,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "authentication": {"credentialz": {"foo": "bar"}},
                "expected_response": KafkaSourceManagerError,
            },
        ]
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            with self.assertRaises(test.get("expected_response")):
                client.get_authentication_for_provider(test.get("provider_type"), test.get("authentication"))

    def test_get_billing_source_for_provider(self):
        """Test to build Koku Provider billing_source json obj."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "billing_source": {"bucket": "test-bucket"},
                "expected_response": {"bucket": "test-bucket"},
            },
            {
                "provider_type": Provider.PROVIDER_OCP,
                "billing_source": {"bucket": ""},
                "expected_response": {"bucket": ""},
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"data_source": {"foo": "bar"}},
                "expected_response": {"data_source": {"foo": "bar"}},
            },
        ]
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            response = client.get_billing_source_for_provider(test.get("provider_type"), test.get("billing_source"))
            self.assertEqual(response, test.get("expected_response"))

    def test_get_billing_source_for_provider_error(self):
        """Test to build Koku Provider billing_source json obj with errors."""
        test_matrix = [
            {
                "provider_type": Provider.PROVIDER_AWS,
                "billing_source": {"data_source": "test-bucket"},
                "expected_response": KafkaSourceManagerError,
            },
            {
                "provider_type": Provider.PROVIDER_AZURE,
                "billing_source": {"bucket": {"foo": "bar"}},
                "expected_response": KafkaSourceManagerError,
            },
        ]
        client = KafkaSourceManager(auth_header=Config.SOURCES_FAKE_HEADER)

        for test in test_matrix:
            with self.assertRaises(test.get("expected_response")):
                client.get_billing_source_for_provider(test.get("provider_type"), test.get("billing_source"))
