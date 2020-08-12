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
"""Test the sources view."""
import json
from random import randint
from unittest.mock import Mock
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

import requests_mock
from django.test.utils import override_settings
from django.urls import reverse

from api.common.permissions import RESOURCE_TYPE_MAP
from api.common.permissions.aws_access import AwsAccessPermission
from api.iam.models import Customer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from koku.middleware import IdentityHeaderMiddleware
from sources.api.view import SourcesViewSet


@override_settings(ROOT_URLCONF="sources.urls")
class SourcesViewTests(IamTestCase):
    """Test Cases for the sources endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        self.test_account = "10001"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        self.test_source_id = 1
        name = "Test Azure Source"
        customer_obj = Customer.objects.get(account_id=customer.get("account_id"))
        self.azure_provider = Provider(name=name, type=Provider.PROVIDER_AZURE, customer=customer_obj)
        self.azure_provider.save()

        self.azure_obj = Sources(
            source_id=self.test_source_id,
            auth_header=self.request_context["request"].META,
            account_id=customer.get("account_id"),
            offset=1,
            source_type=Provider.PROVIDER_AZURE,
            name=name,
            authentication={
                "credentials": {"client_id": "test_client", "tenant_id": "test_tenant", "client_secret": "test_secret"}
            },
            source_uuid=self.azure_provider.uuid,
        )
        self.azure_obj.save()

        mock_url = PropertyMock(return_value="http://www.sourcesclient.com/api/v1/sources/")
        SourcesViewSet.url = mock_url

    def test_source_update(self):
        """Test the PATCH endpoint."""
        credentials = {
            "subscription_id": "12345678-1234-5678-1234-567812345678",
            "tenant_id": "12345678-1234-5678-1234-567812345678",
            "client_id": "12345678-1234-5678-1234-567812345678",
        }

        with patch("sources.api.serializers.ServerProxy"):
            with requests_mock.mock() as m:
                m.patch(
                    f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                    status_code=200,
                    json={"credentials": credentials},
                )

                params = {
                    "authentication": {"credentials": {"subscription_id": "this-ain't-real"}},
                    "billing_source": {"data_source": {"resource_group": "group", "storage_account": "storage"}},
                }
                url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

                response = self.client.patch(
                    url, json.dumps(params), content_type="application/json", **self.request_context["request"].META
                )

                self.assertEqual(response.status_code, 200)

    def test_source_update_exception(self):
        """Test the PATCH endpoint with error."""
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.patch(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                json={"credentials": credentials},
            )

            params = '{"credentials: blah}'
            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.patch(
                url, params, content_type="application/json", **self.request_context["request"].META
            )

            self.assertEqual(response.status_code, 400)

    def test_source_put(self):
        """Test the PUT endpoint."""
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.put(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                json={"credentials": credentials},
            )

            params = {"credentials": credentials}
            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.put(
                url, json.dumps(params), content_type="application/json", **self.request_context["request"].META
            )

            self.assertEqual(response.status_code, 405)

    def test_source_list(self):
        """Test the LIST endpoint."""
        with requests_mock.mock() as m:
            m.get("http://www.sourcesclient.com/api/v1/sources/", status_code=200)

            url = reverse("sources-list")

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get("meta").get("count"), 1)

    def test_source_list_other_header(self):
        """Test the LIST endpoint with other auth header not matching test data."""
        user_data = self._create_user_data()
        other_account = "10002"
        customer = self._create_customer_data(account=other_account)
        IdentityHeaderMiddleware.create_customer(other_account)
        request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        with requests_mock.mock() as m:
            m.get("http://www.sourcesclient.com/api/v1/sources/", status_code=200)

            url = reverse("sources-list")

            response = self.client.get(url, content_type="application/json", **request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(body.get("meta").get("count"), 0)

    def test_source_get(self):
        """Test the GET endpoint."""
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertIsNotNone(body)

    def test_source_get_other_header(self):
        """Test the GET endpoint other header not matching test data."""
        user_data = self._create_user_data()

        customer = self._create_customer_data(account="10002")
        request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{self.test_source_id}/",
                status_code=200,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": self.test_source_id})

            response = self.client.get(url, content_type="application/json", **request_context["request"].META)
            self.assertEqual(response.status_code, 404)

    def test_source_destroy_not_allowed(self):
        """Test access to the destroy endpoint."""
        url = reverse("sources-detail", kwargs={"pk": self.test_source_id})
        response = self.client.delete(url, content_type="application/json", **self.request_context["request"].META)
        self.assertEqual(response.status_code, 405)

    @patch("sources.api.view.ProviderManager.provider_statistics", return_value={})
    def test_source_get_stats(self, _):
        """Test the GET status endpoint."""
        url = reverse("sources-stats", kwargs={"pk": self.test_source_id})
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)

    @patch("sources.api.view.ProviderManager", side_effect=ProviderManagerError("test error"))
    def test_source_list_error(self, _):
        """Test provider_linked is False in list when Provider does not exist."""
        url = reverse("sources-list")
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertTrue(body.get("data"))
        self.assertFalse(body.get("data")[0]["provider_linked"])

    @patch("sources.api.view.ProviderManager")
    def test_source_list_provider_success(self, mock_provider_manager):
        """Test provider_linked is False in list when Provider does not exist."""
        provider_manager = ProviderManager(self.azure_provider.uuid)
        mock_provider_manager.return_value = provider_manager
        url = reverse("sources-list")
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertTrue(body.get("data"))
        self.assertTrue(body.get("data")[0]["provider_linked"])
        self.assertTrue(body.get("data")[0]["active"])

    @patch("sources.api.view.ProviderManager", side_effect=ProviderManagerError("test error"))
    def test_source_retrieve_error(self, _):
        """Test provider_linked is False in Source when Provider does not exist."""
        url = reverse("sources-detail", kwargs={"pk": self.test_source_id})
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertFalse(body["provider_linked"])
        self.assertFalse(body["active"])

    @patch("sources.api.view.ProviderManager", side_effect=ProviderManagerError("test error"))
    def test_source_get_stats_error(self, _):
        """Test provider_linked is False in source-stats when Provider does not exist."""
        url = reverse("sources-stats", kwargs={"pk": self.test_source_id})
        response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(body)
        self.assertFalse(body["provider_linked"])

    def test_source_get_random_int(self):
        """Test the GET endpoint with non-existent source int id."""
        source_id = randint(20, 100)
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{source_id}/",
                status_code=404,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": source_id})

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 404)
            self.assertIsNotNone(body)

    def test_source_get_random_uuid(self):
        """Test the GET endpoint with non-existent source uuid."""
        source_id = uuid4()
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{source_id}/",
                status_code=404,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-detail", kwargs={"pk": source_id})

            response = self.client.get(url, content_type="application/json", **self.request_context["request"].META)
            body = response.json()

            self.assertEqual(response.status_code, 404)
            self.assertIsNotNone(body)

    def test_sources_access(self):
        """Test the limiting of source type visibility."""
        mock_user = Mock(admin=True)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        self.assertEqual(excluded, [])

        mock_user = Mock(admin=False, access=None)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        expected = []
        for resource_type in RESOURCE_TYPE_MAP.keys():
            expected.extend(RESOURCE_TYPE_MAP.get(resource_type))
        self.assertEqual(excluded, expected)

        permissions = {AwsAccessPermission.resource_type: {"read": []}}
        mock_user = Mock(admin=False, access=permissions)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        expected = []
        for resource_type in RESOURCE_TYPE_MAP.keys():
            expected.extend(RESOURCE_TYPE_MAP.get(resource_type))
        self.assertEqual(excluded, expected)

        permissions = {AwsAccessPermission.resource_type: {"read": ["*"]}}
        mock_user = Mock(admin=False, access=permissions)
        request = Mock(user=mock_user)
        excluded = SourcesViewSet.get_excludes(request)
        expected = [Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL, Provider.PROVIDER_OCP]
        self.assertEqual(excluded, expected)
