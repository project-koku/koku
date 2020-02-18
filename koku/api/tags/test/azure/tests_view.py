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
"""Test the Azure tag view."""
from urllib.parse import quote_plus
from urllib.parse import urlencode

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.provider.test import create_generic_provider
from api.report.test.azure.helpers import AzureReportDataGenerator
from api.utils import DateHelper


class AzureTagsViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        self.ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)
        _, self.provider = create_generic_provider(Provider.PROVIDER_AZURE, self.headers)
        self.data_generator = AzureReportDataGenerator(self.tenant, self.provider)
        self.data_generator.add_data_to_tenant()

    def test_execute_tags_queries_keys_only(self):
        """Test that tag key data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
        ]

        for case in test_cases:
            url = reverse("azure-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": True,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json().get("data")

            self.assertTrue(data)
            self.assertTrue(isinstance(data, list))
            for tag in data:
                self.assertTrue(isinstance(tag, str))

    def test_execute_tags_queries(self):
        """Test that tag data is for the correct time queries."""
        test_cases = [
            {"value": "-1", "unit": "month", "resolution": "monthly"},
            {"value": "-2", "unit": "month", "resolution": "monthly"},
        ]

        for case in test_cases:
            url = reverse("azure-tags")
            client = APIClient()
            params = {
                "filter[resolution]": case.get("resolution"),
                "filter[time_scope_value]": case.get("value"),
                "filter[time_scope_units]": case.get("unit"),
                "key_only": False,
            }
            url = url + "?" + urlencode(params, quote_via=quote_plus)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json().get("data")

            self.assertTrue(data)
            self.assertTrue(isinstance(data, list))
            for tag in data:
                self.assertTrue(isinstance(tag, dict))
                self.assertIn("key", tag)
                self.assertIn("values", tag)
                self.assertIsNotNone(tag.get("key"))
                self.assertIn(tag.get("values").__class__, [list, str])
                self.assertTrue(tag.get("values"))
