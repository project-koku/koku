#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Kafka Source Manager."""
import logging
from unittest.mock import patch

from faker import Faker
from rest_framework.exceptions import ValidationError

from api.iam.models import Tenant
from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.provider.provider_builder import ProviderBuilder
from api.provider.provider_builder import ProviderBuilderError
from koku.middleware import IdentityHeaderMiddleware
from masu.test.external.downloader.aws import fake_arn
from providers.provider_access import ProviderAccessor
from sources.config import Config

faker = Faker()


class MockSourceObject:
    def __init__(self, name, type, authentication, billing_source, uuid=None, paused=False):
        self.name = name
        self.source_type = type
        self.authentication = authentication
        self.billing_source = billing_source
        self.source_uuid = uuid
        self.koku_uuid = uuid
        self.paused = paused


class ProviderBuilderTest(IamTestCase):
    """Test cases for ProviderBuilder."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.account = "12345"
        cls.org_id = "3333333"
        IdentityHeaderMiddleware.create_customer(cls.account, cls.org_id, "POST")

    def setUp(self):
        """Test case setup."""
        super().setUp()
        self.name = "Test Provider"
        self.provider_type = Provider.PROVIDER_AWS
        self.authentication = {"credentials": {"role_arn": fake_arn()}}
        self.billing_source = {"data_source": {"bucket": "testbillingsource"}}
        self.source_uuid = faker.uuid4()
        self.mock_source = MockSourceObject(
            self.name, self.provider_type, self.authentication, self.billing_source, self.source_uuid
        )

    def test_create_provider(self):
        """Test to create a provider."""
        # Delete tenants
        Tenant.objects.filter(schema_name="org3333333").delete()  # filtering avoids migrating the template0 again
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            mock_source = MockSourceObject(self.name, self.provider_type, self.authentication, self.billing_source)
            provider = client.create_provider_from_source(mock_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_ocp_cluster_register(self):
        """Test to create an OCP provider with a System identity."""
        # Delete tenants
        Tenant.objects.filter(schema_name="org3333333").delete()  # filtering avoids migrating the template0 again
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_CLUSTER_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            mock_source_auth = {"credentials": {"cluster_id": "0bb29135-d6d1-478b-b5b6-6bd129cb6d5d1001"}}
            mock_source = MockSourceObject(self.name, Provider.PROVIDER_OCP, mock_source_auth, None)
            provider = client.create_provider_from_source(mock_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_ocp_cluster_register_sa(self):
        """Test to create an OCP provider with a service account identity."""
        # Delete tenants
        Tenant.objects.filter(schema_name="org3333333").delete()  # filtering avoids migrating the template0 again
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_SERVICE_ACCOUNT_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            mock_source_auth = {"credentials": {"cluster_id": "0bb29135-d6d1-478b-b5b6-6bd129cb6d5d1001"}}
            mock_source = MockSourceObject(self.name, Provider.PROVIDER_OCP, mock_source_auth, None)
            provider = client.create_provider_from_source(mock_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_no_tenant(self):
        """Test to create a provider after tenant was removed."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            mock_source = MockSourceObject(self.name, self.provider_type, self.authentication, self.billing_source)
            provider = client.create_provider_from_source(mock_source)
            self.assertEqual(provider.name, self.name)

    def test_create_provider_with_source_uuid(self):
        """Test to create a provider with source uuid ."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), self.source_uuid)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=faker.md5(), aws_secret_access_key=faker.md5(), aws_session_token=faker.md5()
        ),
    )
    def test_create_provider_exceptions(self, mock_sts):
        """Test to create a provider with a non-recoverable error."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with self.assertRaises(ValidationError):
            client.create_provider_from_source(self.mock_source)

    @patch("masu.celery.tasks.delete_archived_data.delay")
    def test_destroy_provider(self, _):
        """Test to destroy a provider."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), self.source_uuid)
            client.destroy_provider(self.source_uuid)
            with self.assertRaises(Provider.DoesNotExist):
                Provider.objects.get(uuid=self.source_uuid)

    def test_destroy_provider_exception(self):
        """Test to destroy a provider with a connection error."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertEqual(provider.name, self.name)
            self.assertEqual(str(provider.uuid), self.source_uuid)
            logging.disable(logging.NOTSET)
            with self.assertLogs(logger="api.provider.provider_builder", level=logging.INFO):
                client.destroy_provider(faker.uuid4())

    def test_update_provider(self):
        """Test to update a provider."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            new_name = "Aws Test"
            self.mock_source.name = new_name
            updated_provider = client.update_provider_from_source(self.mock_source)
            self.assertEqual(updated_provider.uuid, provider.uuid)
            self.assertEqual(updated_provider.name, new_name)

    def test_update_provider_pause(self):
        """Test to update a provider for pause/unpause."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = client.create_provider_from_source(self.mock_source)
            self.assertFalse(provider.paused)
            for test in [True, False]:
                with self.subTest(paused=test):
                    self.mock_source.paused = test
                    updated_provider = client.update_provider_from_source(self.mock_source)
                    self.assertEqual(updated_provider.paused, test)

    def test_update_provider_exception(self):
        """Test to update a provider with a connection error."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
        with self.assertRaises(Provider.DoesNotExist):
            client.update_provider_from_source(self.mock_source)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=faker.md5(), aws_secret_access_key=faker.md5(), aws_session_token=faker.md5()
        ),
    )
    def test_update_provider_error(self, mock_sts):
        """Test to update a provider with a koku server error."""
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )
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
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )

        for test in test_matrix:
            with self.subTest(test=test):
                response = client._build_credentials_auth(test.get("provider_type"), test.get("authentication"))
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
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )

        for test in test_matrix:
            with self.assertRaises(test.get("expected_response")):
                client._build_credentials_auth(test.get("provider_type"), test.get("authentication"))

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
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )

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
        client = ProviderBuilder(
            auth_header=Config.SOURCES_FAKE_HEADER, account_number=self.account, org_id=self.org_id
        )

        for test in test_matrix:
            with self.assertRaises(test.get("expected_response")):
                client.get_billing_source_for_provider(test.get("provider_type"), test.get("billing_source"))
