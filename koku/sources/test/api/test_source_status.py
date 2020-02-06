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

from api.provider.models import Provider
from api.provider.models import Sources
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from faker import Faker
from providers.provider_access import ProviderAccessor
from rest_framework import status
from rest_framework.test import APIClient
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError

faker = Faker()


@override_settings(ROOT_URLCONF="sources.urls")
class SourcesStatusTest(TestCase):
    """Source Status Test Class."""

    def test_http_endpoint_source_not_found(self):
        """
        Test sources status returns 404 when source isn't found.

        When there's no provider or source, the endpoint should return 404.
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url + "?source_id=1")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mock_response_returns_false(self):
        """
        Test sources status returns False.

        This test ensures that a mock response contains the payload 'False'
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url + "?source_id=1")
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
        response = client.get(url + "?source_id=1")
        mock_response = create_autospec(response, data=True, status=status.HTTP_200_OK)
        mock_response_source_status = mock_response.data
        expected_source_status = True
        expected_HTTP_code = status.HTTP_200_OK
        self.assertEqual(mock_response_source_status, expected_source_status)
        self.assertEqual(mock_response.status, expected_HTTP_code)

    def test_success(self):
        """Test that the API returns status when a source is configured correctly."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(ProviderAccessor, "availability_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="",
                offset=1,
            )
            response = client.get(url + "?source_id=1")
            actual_source_status = response.data
            self.assertEquals(mock_status, actual_source_status)

    def test_missing_query_parameter(self):
        """
        Test when the user accesses this API without giving a parameter for example '?source_id=1'.

        The API should respond with an error that there is a missing query paramter 'source_id'
        The API should respond with HTTP_400_BAD_REQUEST
        """
        url = reverse("source-status")
        client = APIClient()
        response = client.get(url)
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
        response = client.get(url + "?source_id=string")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, "source_id must be an integer")

    def test_validation_error_causes_unavailable_status(self):
        """
        Test when an unavailable status is returned by ProviderAccessor.availability_status().

        The API should return the appropriate status response.
        """
        mock_status = {"availability_status": "unavailable", "availability_status_error": "error msg"}
        with patch.object(ProviderAccessor, "availability_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={},
                billing_source={"bucket": "hi"},
                koku_uuid="",
                offset=1,
            )
            response = client.get(url + "?source_id=1")
            actual_source_status = response.data
            self.assertEquals(mock_status, actual_source_status)

    def test_billing_source_data_source(self):
        """
        Test when billing_source contains 'data_source' instead of 'bucket'.

        Test when a ValidationError occurs in ProviderAccessor.availability_status().
        The API should return data=True.
        """
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(ProviderAccessor, "availability_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"credentials": "hi"},
                billing_source={"data_source": "ho"},
                koku_uuid="",
                offset=1,
            )
            response = client.get(url + "?source_id=1")
            actual_source_status = response.data
            self.assertEquals(mock_status, actual_source_status)

    def test_authentication_resource_name(self):
        """Test when the authentication is named 'resource_name' instead of 'credentials'."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(ProviderAccessor, "availability_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={"resource_name": "ho"},
                billing_source={"data_source": "hi"},
                koku_uuid="",
                offset=1,
            )
            response = client.get(url + "?source_id=1")
            actual_source_status = response.data
            self.assertEquals(mock_status, actual_source_status)

    def test_post_status(self):
        """Test that the API pushes sources status with POST."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(ProviderAccessor, "availability_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="",
                offset=1,
            )
            json_data = {"source_id": 1}
            with patch.object(SourcesHTTPClient, "set_source_status", return_value=True):
                response = client.post(url, data=json_data)
            self.assertEquals(response.status_code, 204)

    def test_post_status_error(self):
        """Test that the API pushes sources status with POST with connection error."""
        mock_status = {"availability_status": "available", "availability_status_error": ""}
        with patch.object(ProviderAccessor, "availability_status", return_value=mock_status):
            url = reverse("source-status")
            client = APIClient()
            # Insert a source with ID 1
            Sources.objects.create(
                source_id=1,
                name="New AWS Mock Test Source",
                source_type=Provider.PROVIDER_AWS,
                authentication={},
                billing_source={"bucket": "my-bucket"},
                koku_uuid="",
                offset=1,
            )
            json_data = {"source_id": 1}
            with patch.object(SourcesHTTPClient, "set_source_status", side_effect=SourcesHTTPClientError):
                response = client.post(url, data=json_data)
            self.assertEquals(response.status_code, 204)
