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
from providers.provider_access import ProviderAccessor
from providers.provider_errors import ProviderErrors
from sources.api.source_status import SourceStatus
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError

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
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"authentication": {"rolearn": "myarn"}},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="",
                offset=1,
            )
            json_data = {"source_id": 1}
            with patch.object(SourcesHTTPClient, "set_source_status", return_value=True):
                response = client.post(url, data=json_data, **self.headers)
            self.assertEquals(response.status_code, 204)

    def test_post_status_error(self):
        """Test that the API pushes sources status with POST with connection error."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(SourcesHTTPClient, "build_source_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"authentication": {"rolearn": "myarn"}},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="",
                offset=1,
            )
            json_data = {"source_id": 1}
            with patch.object(SourcesHTTPClient, "set_source_status", side_effect=SourcesHTTPClientError):
                response = client.post(url, data=json_data, **self.headers)
            self.assertEquals(response.status_code, 204)

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
                "billing_source": {"data_source": {"dataset": "test_dataset", "table_id": "test_table"}},
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
                    actual_source_status = response.data
                    self.assertEquals("available", actual_source_status.get("availability_status"))
                    self.assertTrue(Provider.objects.get(uuid=provider.uuid).active)

    def test_aws_unavailable(self):
        """Test that the API returns status when a source is configured correctly."""
        url = reverse("source-status")
        client = APIClient()
        # Insert a source with ID 1
        Sources.objects.create(
            source_id=1,
            name="New AWS Mock Test Source",
            source_type=Provider.PROVIDER_AWS,
            authentication={"credentials": {"role_arn": "fake-iam"}},
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
        self.assertEquals(actual_source_status, expected)

    def test_azure_unavailable(self):
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
        expected = {
            "availability_status": "unavailable",
            "availability_status_error": ProviderErrors.AZURE_INCORRECT_CLIENT_ID_MESSAGE,
        }
        self.assertEquals(actual_source_status, expected)

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
        self.assertEquals(actual_source_status, expected)

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
            status_obj = SourceStatus(request, source_id)
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
            status_obj = SourceStatus(request, source_id)
            status_obj.status()

            self.assertFalse(Provider.objects.get(uuid=provider.uuid).active)

    def test_post_status_wrong_provider(self):
        """Test for logs when provider mismatch is detected while setting status."""
        request = self.request_context.get("request")
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
            status_obj = SourceStatus(request, source_id)
            with self.assertLogs("sources.api.source_status", level="INFO") as logger:
                status_obj.status()
                expected = f"INFO:sources.api.source_status:No provider found for Source ID: {source_id}"
                self.assertIn(expected, logger.output)
