#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Sources Status HTTP Client."""
from unittest.mock import create_autospec
from unittest.mock import patch
from uuid import uuid4

from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker
from rest_framework import status
from rest_framework.serializers import ValidationError
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from masu.test.external.downloader.aws import fake_arn
from providers.provider_access import ProviderAccessor
from providers.provider_errors import ProviderErrors
from sources.api.source_status import SourceStatus
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError
from sources.sources_provider_coordinator import SourcesProviderCoordinator

faker = Faker()


@override_settings(ROOT_URLCONF="sources.urls")
class SourcesStatusTest(IamTestCase):
    """Source Status Test Class."""

    def test_http_endpoint_source_not_found(self):
        """
        Test sources status returns 404 when source isn't found.

        When there's no provider or source, the endpoint should return 404.
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url + "?source_id=1", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mock_response_returns_false(self):
        """
        Test sources status returns False.

        This test ensures that a mock response contains the payload 'False'
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url + "?source_id=1", **self.headers)
        mock_response = create_autospec(response, data=False, status=status.HTTP_200_OK)
        mock_response_source_status = mock_response.data
        expected_source_status = False
        expected_HTTP_code = status.HTTP_200_OK
        self.assertEqual(mock_response_source_status, expected_source_status)
        self.assertEqual(mock_response.status, expected_HTTP_code)

    def test_mock_response_returns_true(self):
        """
        Test sources status returns True.

        response.data should contain a True value.
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url + "?source_id=1", **self.headers)
        mock_response = create_autospec(response, data=True, status=status.HTTP_200_OK)
        mock_response_source_status = mock_response.data
        expected_source_status = True
        expected_HTTP_code = status.HTTP_200_OK
        self.assertEqual(mock_response_source_status, expected_source_status)
        self.assertEqual(mock_response.status, expected_HTTP_code)

    def test_missing_query_parameter(self):
        """
        Test when the user accesses this API without giving a parameter for example '?source_id=1'.

        The API should respond with an error that there is a missing query paramter 'source_id'
        The API should respond with HTTP_400_BAD_REQUEST
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "Missing query parameter source_id")

    def test_source_id_not_integer(self):
        """
        Test when the user accesses this API when giving a parameter for example '?source_id=string'.

        The API should respond with an error that the source_id must be an integer
        The API should respond with HTTP_400_BAD_REQUEST
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url + "?source_id=string", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "source_id must be an integer")

    def test_post_status(self):
        """Test that the API pushes sources status with POST."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Use a valid UUID so Provider.objects.get(uuid=...) does not raise ValidationError
            provider = Provider.objects.create(
                name="Test AWS Provider",
                created_by=self.request_context["request"].user,
                customer=self.request_context["request"].user.customer,
                active=True,
            )
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"authentication": {"rolearn": "myarn"}},
                billing_source={"bucket": "my-bucket"},
                koku_uuid=str(provider.uuid),
                offset=1,
            )
            json_data = {"source_id": 1}
            with patch.object(SourcesHTTPClient, "set_source_status", return_value=True):
                response = client.post(url, data=json_data, **self.headers)
            self.assertEqual(response.status_code, 204)

    @patch("sources.api.source_status.SourcesProviderCoordinator.create_account")
    @patch("sources.api.source_status.SourcesProviderCoordinator.update_account")
    @patch("sources.api.source_status.SourcesHTTPClient.set_source_status")
    def test_push_status_first_gcp_table_discovery(
        self, mock_set_source_status, mock_update_account, mock_create_account
    ):
        """Test that push_status for initial discovery of GCP BigQuery table id."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            test_source_id = 1
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=test_source_id,
                name="New GCP Mock Test Source",
                source_type=Provider.PROVIDER_GCP,
                authentication={"credentials": {"project_id": "test_project_id"}},
                billing_source={"data_source": {"dataset": "test_dataset", "table_id": "cost_table"}},
                status={},
                offset=1,
            )

            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                with patch.object(SourceStatus, "update_source_name", returns=True):
                    with patch.object(SourceStatus, "_set_provider_active_status", returns=True):
                        status_obj = SourceStatus(test_source_id)
                        status_obj.push_status()
                        mock_set_source_status.assert_called()
                        mock_create_account.assert_called()
                        mock_update_account.assert_not_called()

    @patch("sources.api.source_status.SourcesProviderCoordinator.create_account")
    @patch("sources.api.source_status.SourcesProviderCoordinator.update_account")
    @patch("sources.api.source_status.SourcesHTTPClient.set_source_status")
    def test_push_status_first_gcp_table_discovery_update(
        self, mock_set_source_status, mock_update_account, mock_create_account
    ):
        """Test that push_status for initial discovery of GCP BigQuery table id after dataset was updated."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            test_source_id = 1
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=test_source_id,
                name="New GCP Mock Test Source",
                source_type=Provider.PROVIDER_GCP,
                koku_uuid=faker.uuid4(),
                authentication={"credentials": {"project_id": "test_project_id"}},
                billing_source={"data_source": {"dataset": "test_dataset"}},
                status={},
                offset=1,
            )

            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                with patch.object(SourceStatus, "update_source_name", returns=True):
                    with patch.object(SourceStatus, "_set_provider_active_status", returns=True):
                        status_obj = SourceStatus(test_source_id)
                        status_obj.push_status()
                        mock_set_source_status.assert_called()
                        mock_create_account.assert_not_called()
                        mock_update_account.assert_called()

    @patch("sources.api.source_status.SourcesHTTPClient.set_source_status")
    def test_push_status_second_gcp_table_discovery(self, mock_set_source_status):
        """Test that push_status for when GCP BigQuery table id is not already known."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            test_source_id = 1
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=test_source_id,
                name="New GCP Mock Test Source",
                source_type=Provider.PROVIDER_GCP,
                authentication={"credentials": {"project_id": "test_project_id"}},
                billing_source={"data_source": {"dataset": "test_dataset"}},
                status={"availability_status": "available", "availability_status_error": ""},
                offset=1,
            )

            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                with patch.object(SourceStatus, "update_source_name", returns=True):
                    with patch.object(SourcesProviderCoordinator, "create_account", returns=True):
                        status_obj = SourceStatus(test_source_id)
                        status_obj.push_status()
                        mock_set_source_status.assert_called()

    @patch("sources.api.source_status.SourcesHTTPClient.set_source_status")
    def test_push_status_second_gcp_table_discovery_validation_error(self, mock_set_source_status):
        """Test that push_status catches validation error during `create_account` and pushes status."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            test_source_id = 1
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=test_source_id,
                name="New GCP Mock Test Source",
                source_type=Provider.PROVIDER_GCP,
                authentication={"credentials": {"project_id": "test_project_id"}},
                billing_source={"data_source": {"dataset": "test_dataset", "table_id": "billtable"}},
                status={"availability_status": "available", "availability_status_error": ""},
                offset=1,
            )

            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                with patch.object(SourceStatus, "update_source_name", returns=True):
                    with patch.object(SourcesProviderCoordinator, "create_account", side_effect=ValidationError):
                        status_obj = SourceStatus(test_source_id)
                        status_obj.push_status()
                        mock_set_source_status.assert_called()

    @patch("sources.api.source_status.SourcesHTTPClient.set_source_status")
    def test_push_status_gcp_table_discovery_completed(self, mock_set_source_status):
        """Test that push_status for when GCP BigQuery table id is already known."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            test_source_id = 1
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=test_source_id,
                name="New GCP Mock Test Source",
                source_type=Provider.PROVIDER_GCP,
                koku_uuid=faker.uuid4(),
                authentication={"credentials": {"project_id": "test_project_id"}},
                billing_source={"data_source": {"dataset": "test_dataset", "table_id": "billtable"}},
                status={"availability_status": "available", "availability_status_error": ""},
                offset=1,
            )

            with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                with patch.object(SourceStatus, "update_source_name", returns=True):
                    with patch.object(SourcesProviderCoordinator, "update_account", returns=True):
                        status_obj = SourceStatus(test_source_id)
                        status_obj.push_status()
                        mock_set_source_status.assert_called()

    @patch("sources.api.source_status.SourcesProviderCoordinator.update_account")
    @patch("sources.api.source_status.SourcesHTTPClient.get_source_details")
    def test_update_source_name(self, mock_get_source_details, mock_update_account):
        """Test that the source name is queued for update when out of sync with platform."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}

        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            # Insert a source with ID 1
            test_source_id = 1
            Sources.objects.create(
                source_id=test_source_id,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"authentication": {"rolearn": "myarn"}},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="uuid",
                offset=1,
            )

            status_obj = SourceStatus(test_source_id)
            with patch.object(
                SourcesHTTPClient, "get_source_details", return_value={"name": "New Name", "source_type_id": "1"}
            ):
                status_obj.update_source_name()
                mock_update_account.assert_called()

    @patch("sources.api.source_status.SourcesProviderCoordinator.update_account")
    @patch("sources.api.source_status.SourcesHTTPClient.get_source_details")
    def test_update_source_name_no_change(self, mock_get_source_details, mock_update_account):
        """Test that the source name is not queued for update when out of sync with platform."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        source_name = "AWS source"
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            # Insert a source with ID 1
            test_source_id = 1
            Sources.objects.create(
                source_id=test_source_id,
                name=source_name,
                source_type=Provider.PROVIDER_AWS,
                authentication={"authentication": {"rolearn": "myarn"}},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="uuid",
                offset=1,
            )

            status_obj = SourceStatus(test_source_id)
            with patch.object(
                SourcesHTTPClient, "get_source_details", return_value={"name": source_name, "source_type_id": "1"}
            ):
                status_obj.update_source_name()
                mock_update_account.assert_not_called()

    def test_post_status_error(self):
        """Test that the API pushes sources status with POST with connection error."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Use a valid UUID so Provider.objects.get(uuid=...) does not raise ValidationError
            provider = Provider.objects.create(
                name="Test AWS Provider",
                created_by=self.request_context["request"].user,
                customer=self.request_context["request"].user.customer,
                active=True,
            )
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"authentication": {"rolearn": "myarn"}},
                billing_source={"bucket": "my-bucket"},
                koku_uuid=str(provider.uuid),
                offset=1,
            )
            json_data = {"source_id": 1}
            with patch.object(SourcesHTTPClient, "set_source_status", side_effect=SourcesHTTPClientError):
                response = client.post(url, data=json_data, **self.headers)
            self.assertEqual(response.status_code, 204)

    def test_available(self):
        """Test that availability status is available when cost_usage_source_ready is True."""
        request = self.request_context.get("request")
        test_matrix = [
            {
                "name": "New AWS Mock Test Source",
                "source_type": Provider.PROVIDER_AWS,
                "authentication": {"credentials": {"role_arn": "fake-iam"}},
                "billing_source": {"data_source": {"bucket": "my-bucket"}},
                "offset": 1,
            },
            {
                "name": "New Azure Mock Test Source",
                "source_type": Provider.PROVIDER_AZURE,
                "authentication": {
                    "credentials": {
                        "subscription_id": "subid",
                        "client_id": "testid",
                        "tenant_id": "tenant",
                        "client_secret": "secret",
                    }
                },
                "billing_source": {"data_source": {"resource_group": "rg", "storage_account": "sa"}},
                "offset": 1,
            },
            {
                "name": "New OCP Mock Test Source",
                "source_type": Provider.PROVIDER_OCP,
                "authentication": {"credentials": {"cluster_id": "cluster_id"}},
                "offset": 1,
            },
            {
                "name": "New GCP Mock Test Source",
                "source_type": Provider.PROVIDER_GCP,
                "authentication": {"credentials": {"project_id": "test_project_id"}},
                "billing_source": {"data_source": {"dataset": "test_dataset"}},
                "offset": 1,
            },
        ]
        for i, test in enumerate(test_matrix):
            with self.subTest(test=test):
                with patch.object(ProviderAccessor, "cost_usage_source_ready", return_value=True):
                    provider = Provider.objects.create(
                        name=test.get("name"), created_by=request.user, customer=request.user.customer, active=True
                    )
                    test["koku_uuid"] = str(provider.uuid)
                    url = reverse("source-status")
                    client = APIClient()
                    # Insert a source with ID 1
                    Sources.objects.create(source_id=i, **test)
                    response = client.get(url + f"?source_id={i}", **self.headers)
                    actual_source_status = response.data
                    self.assertEqual("available", actual_source_status.get("availability_status"))
                    self.assertTrue(Provider.objects.get(uuid=provider.uuid).active)

    @override_settings(
        DEMO_ACCOUNTS={"123": {"arn:aws:iam::999:role/DEMO": {"report_prefix": "cur", "report_name": "awscost"}}}
    )
    @patch("sources.api.source_status.SourcesHTTPClient.get_source_details")
    def test_available_demo_accounts(self, mock_cost_usage_ready):
        """Test avaiability status for demo accounts."""
        test_source_id = 3
        source_json = {
            "name": "New AWS Mock Test Source",
            "source_type": Provider.PROVIDER_AWS,
            "source_id": test_source_id,
            "account_id": 123,
            "authentication": {"credentials": {"role_arn": "fake-iam"}},
            "billing_source": {"data_source": {"bucket": "my-bucket"}},
            "offset": 1,
        }

        source_json["koku_uuid"] = faker.uuid4()
        url = reverse("source-status")
        client = APIClient()
        # Insert a source with ID 1
        Sources.objects.create(**source_json)
        _ = client.get(url + f"?source_id={test_source_id}", **self.headers)
        mock_cost_usage_ready.assert_not_called()

    def test_not_ready_for_status(self):
        """Test that availability status when source is not ready for status check."""
        request = self.request_context.get("request")
        test_matrix = [
            {
                "name": "New AWS Mock Test Source",
                "source_type": Provider.PROVIDER_AWS,
                "authentication": {},
                "billing_source": {"data_source": {"bucket": "my-bucket"}},
                "offset": 1,
            },
            {
                "name": "New Azure Mock Test Source",
                "source_type": Provider.PROVIDER_AZURE,
                "authentication": {
                    "credentials": {"client_id": "testid", "tenant_id": "tenant", "client_secret": "secret"}
                },
                "billing_source": {"data_source": {"resource_group": "rg", "storage_account": "sa"}},
                "offset": 1,
            },
            {
                "name": "New Azure Mock Test Source 2",
                "source_type": Provider.PROVIDER_AZURE,
                "authentication": {
                    "credentials": {
                        "subscription_id": "subid",
                        "client_id": "testid",
                        "tenant_id": "tenant",
                        "client_secret": "secret",
                    }
                },
                "billing_source": {"data_source": {"storage_account": "sa"}},
                "offset": 1,
            },
            {
                "name": "New Azure Mock Test Source 3",
                "source_type": Provider.PROVIDER_AZURE,
                "authentication": {
                    "credentials": {
                        "subscription_id": "subid",
                        "client_id": "testid",
                        "tenant_id": "tenant",
                        "client_secret": "secret",
                    }
                },
                "billing_source": {},
                "offset": 1,
            },
            {
                "name": "New Azure Mock Test Source 4",
                "source_type": Provider.PROVIDER_AZURE,
                "authentication": {},
                "billing_source": {"data_source": {"resource_group": "rg", "storage_account": "sa"}},
                "offset": 1,
            },
            {
                "name": "New OCP Mock Test Source",
                "source_type": Provider.PROVIDER_OCP,
                "authentication": {},
                "offset": 1,
            },
            {
                "name": "New GCP Mock Test Source",
                "source_type": Provider.PROVIDER_GCP,
                "authentication": {"credentials": {"project_id": "test_project_id"}},
                "billing_source": {},
                "offset": 1,
            },
        ]
        for i, test in enumerate(test_matrix):
            with self.subTest(test=test):
                with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
                    provider = Provider.objects.create(
                        name=test.get("name"), created_by=request.user, customer=request.user.customer, active=True
                    )
                    test["koku_uuid"] = str(provider.uuid)
                    url = reverse("source-status")
                    client = APIClient()
                    # Insert a source with ID 1
                    Sources.objects.create(source_id=i, **test)
                    response = client.get(url + f"?source_id={i}", **self.headers)
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_aws_unavailable(self):
        """Test that the API returns status when a source is configured correctly."""
        url = reverse("source-status")
        client = APIClient()
        # Insert a source with ID 1
        Sources.objects.create(
            source_id=1,
            name="New AWS Mock Test Source",
            source_type=Provider.PROVIDER_AWS,
            authentication={"credentials": {"role_arn": fake_arn()}},
            billing_source={"data_source": {"bucket": "my-bucket"}},
            koku_uuid=faker.uuid4(),
            offset=1,
        )
        response = client.get(url + "?source_id=1", **self.headers)
        actual_source_status = response.data
        expected = {
            "availability_status": "unavailable",
            "availability_status_error": ProviderErrors.AWS_ROLE_ARN_UNREACHABLE_MESSAGE,
        }
        self.assertEqual(actual_source_status, expected)

    @patch("providers.azure.client.ClientSecretCredential")
    def test_azure_unavailable(self, mock_client_credential):
        """Test that the API returns status when a source is configured correctly."""
        url = reverse("source-status")
        client = APIClient()
        # Insert a source with ID 1
        credentials = {
            "subscription_id": faker.uuid4(),
            "tenant_id": faker.uuid4(),
            "client_id": faker.uuid4(),
            "client_secret": faker.word(),
        }
        data_source = {"resource_group": faker.word(), "storage_account": faker.word()}
        Sources.objects.create(
            source_id=1,
            name="New Azure Mock Test Source",
            source_type=Provider.PROVIDER_AZURE,
            authentication={"credentials": credentials},
            billing_source={"data_source": data_source},
            koku_uuid=faker.uuid4(),
            offset=1,
        )
        response = client.get(url + "?source_id=1", **self.headers)
        actual_source_status = response.data

        self.assertEqual(actual_source_status.get("availability_status"), "unavailable")
        self.assertIn("SubscriptionNotFound", actual_source_status.get("availability_status_error"))

    def test_ocp_unavailable(self):
        """Test that the API returns status when a source is configured correctly."""
        url = reverse("source-status")
        client = APIClient()

        # Insert a source with ID 1
        Sources.objects.create(
            source_id=1,
            name="New OCP Mock Test Source",
            source_type=Provider.PROVIDER_OCP,
            authentication={"credentials": {"provider_resoure_name": ""}},
            billing_source={"data_source": {}},
            koku_uuid=faker.uuid4(),
            offset=1,
        )
        response = client.get(url + "?source_id=1", **self.headers)
        actual_source_status = response.data
        expected = {
            "availability_status": "unavailable",
            "availability_status_error": "Provider resource name is a required parameter for OCP.",
        }
        self.assertEqual(actual_source_status, expected)

    # TODO double check these new tests
    def test_post_status_provider_available(self):
        """Test that the provider active flag is set to true when source is available."""
        request = self.request_context.get("request")
        source_id = 1
        source_name = "New AWS Mock Test Source"
        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            provider = Provider.objects.create(
                name=source_name, created_by=request.user, customer=request.user.customer, active=False
            )

            Sources.objects.create(
                source_id=1,
                name=source_name,
                source_type=Provider.PROVIDER_AWS,
                authentication={"credentials": {"role_arn": "fake-iam"}},
                billing_source={"data_source": {"bucket": "my-bucket"}},
                koku_uuid=str(provider.uuid),
                offset=1,
            )
            status_obj = SourceStatus(source_id)
            status_obj.status()

            self.assertTrue(Provider.objects.get(uuid=provider.uuid).active)

    def test_post_status_provider_unavailable(self):
        """Test that the provider active flag is set to true when source is unavailable."""
        request = self.request_context.get("request")
        source_id = 1
        source_name = "New AWS Mock Test Source"

        with patch.object(ProviderAccessor, "cost_usage_source_ready", side_effect=ValidationError("test error")):
            provider = Provider.objects.create(
                name=source_name, created_by=request.user, customer=request.user.customer, active=True
            )

            Sources.objects.create(
                source_id=1,
                name=source_name,
                source_type=Provider.PROVIDER_AWS,
                authentication={"credentials": {"role_arn": "fake-iam"}},
                billing_source={"data_source": {"bucket": "my-bucket"}},
                koku_uuid=str(provider.uuid),
                offset=1,
            )
            status_obj = SourceStatus(source_id)
            status_obj.status()

            self.assertFalse(Provider.objects.get(uuid=provider.uuid).active)

    def test_post_status_wrong_provider(self):
        """Test for logs when provider mismatch is detected while setting status."""
        source_id = 1
        source_name = "New AWS Mock Test Source"

        with patch.object(ProviderAccessor, "cost_usage_source_ready", returns=True):
            Sources.objects.create(
                source_id=source_id,
                name=source_name,
                source_type=Provider.PROVIDER_AWS,
                authentication={"credentials": {"role_arn": "fake-iam"}},
                billing_source={"data_source": {"bucket": "my-bucket"}},
                koku_uuid=str(uuid4()),
                offset=1,
            )
            status_obj = SourceStatus(source_id)
            with self.assertLogs("sources.api.source_status", level="INFO") as logger:
                status_obj.status()
                expected = f"INFO:sources.api.source_status:No provider found for Source ID: {source_id}"
                self.assertIn(expected, logger.output)

    def test_post_source_status_success(self):
        """Test that POST to source_status works correctly when source_id is valid."""
        url = reverse("source-status")
        client = APIClient()

        source = Sources.objects.create(
            source_id=1,
            name="Test Source",
            source_type=Provider.PROVIDER_AWS,
            authentication={"credentials": {"role_arn": "fake-iam"}},
            billing_source={"data_source": {"bucket": "my-bucket"}},
            offset=1,
        )
        payload = {"source_id": source.source_id}
        response = client.post(url, data=payload, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_post_source_status_missing_source_id(self):
        """Test that POST returns 400 if source_id is missing."""
        url = reverse("source-status")
        client = APIClient()
        payload = {}
        response = client.post(url, data=payload, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "Missing query parameter source_id")

    def test_post_source_status_invalid_source_id(self):
        """Test that POST returns 400 if source_id is not an integer."""
        url = reverse("source-status")
        client = APIClient()
        payload = {"source_id": "invalid_id"}
        response = client.post(url, data=payload, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "source_id must be an integer")

    def test_post_source_status_source_not_found(self):
        url = reverse("source-status")
        client = APIClient()
        payload = {"source_id": 99999999}
        response = client.post(url, data=payload, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
