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
"""Test the sources proxy view."""
import json
from unittest.mock import PropertyMock

import requests
import requests_mock
from django.test import TestCase
from django.urls import reverse
from faker import Faker

from api.sources.view import SourcesProxyViewSet

faker = Faker()


class SourcesViewProxyTests(TestCase):
    """Test Cases for the sources proxy endpoint."""

    def setUp(self):
        """Set up tests."""
        super().setUp()
        mock_url = PropertyMock(return_value="http://www.sourcesclient.com/api/v1/sources/")
        SourcesProxyViewSet.url = mock_url

    def test_update_proxy(self):
        """Test the PATCH proxy endpoint."""
        test_source_id = 1
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.patch(
                f"http://www.sourcesclient.com/api/v1/sources/{test_source_id}/",
                status_code=200,
                json={"credentials": credentials},
                headers={"Content-Type": "application/json"},
            )

            params = {"credentials": credentials}
            url = reverse("sources-proxy-detail", kwargs={"source_id": test_source_id})

            response = self.client.patch(url, json.dumps(params), content_type="application/json")

            body = response.json()

            self.assertEqual(response.status_code, 200)
            self.assertIn(str(credentials), str(body))

    def test_update_proxy_connection_error(self):
        """Test the PATCH proxy endpoint with connection error."""
        test_source_id = 1
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.patch(
                f"http://www.sourcesclient.com/api/v1/sources/{test_source_id}/",
                exc=requests.exceptions.ConnectionError,
            )

            params = {"credentials": credentials}
            url = reverse("sources-proxy-detail", kwargs={"source_id": test_source_id})

            response = self.client.patch(url, json.dumps(params), content_type="application/json")

            self.assertEqual(response.status_code, 500)

    def test_update_put_proxy(self):
        """Test the PUT proxy endpoint."""
        test_source_id = 1
        credentials = {"subscription_id": "subscription-uuid"}

        with requests_mock.mock() as m:
            m.patch(
                f"http://www.sourcesclient.com/api/v1/sources/{test_source_id}/",
                status_code=200,
                json={"credentials": credentials},
                headers={"Content-Type": "application/json"},
            )

            params = {"credentials": credentials}
            url = reverse("sources-proxy-detail", kwargs={"source_id": test_source_id})

            response = self.client.put(url, json.dumps(params), content_type="application/json")
            self.assertEqual(response.status_code, 405)

    def test_list_proxy(self):
        """Test the LIST proxy endpoint."""
        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/",
                status_code=200,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-proxy-list")

            response = self.client.get(url, content_type="application/json")

            self.assertEqual(response.status_code, 200)

    def test_list_proxy_connection_error(self):
        """Test the LIST proxy endpoint with connection error."""
        with requests_mock.mock() as m:
            m.get(f"http://www.sourcesclient.com/api/v1/sources/", exc=requests.exceptions.ConnectionError)

            url = reverse("sources-proxy-list")

            response = self.client.get(url, content_type="application/json")

            self.assertEqual(response.status_code, 500)

    def test_get_proxy(self):
        """Test the GET proxy endpoint."""
        test_source_id = 1

        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{test_source_id}/",
                status_code=200,
                headers={"Content-Type": "application/json"},
            )

            url = reverse("sources-proxy-detail", kwargs={"source_id": test_source_id})

            response = self.client.get(url, content_type="application/json")

            self.assertEqual(response.status_code, 200)

    def test_get_proxy_connection_error(self):
        """Test the GET proxy endpoint with connection error."""
        test_source_id = 1

        with requests_mock.mock() as m:
            m.get(
                f"http://www.sourcesclient.com/api/v1/sources/{test_source_id}/",
                exc=requests.exceptions.ConnectionError,
            )

            url = reverse("sources-proxy-detail", kwargs={"source_id": test_source_id})

            response = self.client.get(url, content_type="application/json")

            self.assertEqual(response.status_code, 500)
