#
# Copyright 2020 Red Hat, Inc.
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
"""Test the crawl_account_hierarchy endpoint view."""
from unittest.mock import patch
from urllib.parse import urlencode

from django.test.utils import override_settings
from django.urls import reverse

from masu.test import MasuTestCase


@override_settings(ROOT_URLCONF="masu.urls")
class crawlAccountHierarchyTest(MasuTestCase):
    """Test Cases for the crawl_account_hierarchy endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.crawl_account_hierarchy.crawl_hierarchy")
    def test_get_crawl_account_hierarchy(self, mock_update, _):
        """Test the GET crawl_account_hierarchy endpoint."""
        params = {"provider_uuid": self.aws_test_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        response = self.client.get(url)
        body = response.json()
        expected_key = "Crawl Account Hierarchy Task ID"
        self.assertIsNotNone(body.get(expected_key))
        self.assertEqual(response.status_code, 200)
        mock_update.delay.assert_called_with(provider_uuid=self.aws_test_provider_uuid)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_crawl_account_hierarchy_bad_provider_uuid(self, _):
        """Test the GET crawl_account_hierarchy endpoint with bad provider uuid."""
        bad_provider_uuid = "bad_provider_uuid"
        params = {"provider_uuid": bad_provider_uuid}
        query_string = urlencode(params)
        url = reverse("crawl_account_hierarchy") + "?" + query_string
        expected_errmsg = f"The provider_uuid {bad_provider_uuid} does not exist."
        response = self.client.get(url)
        body = response.json()
        errmsg = body.get("Error")
        self.assertIsNotNone(errmsg)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)

    @patch("koku.middleware.MASU", return_value=True)
    def test_require_provider_uuid(self, _):
        """Test the GET crawl_account_hierarchy endpoint with no provider uuid."""
        response = self.client.get(reverse("crawl_account_hierarchy"))
        body = response.json()
        errmsg = body.get("Error")
        expected_errmsg = "provider_uuid is a required parameter."
        self.assertEqual(response.status_code, 400)
        self.assertEqual(errmsg, expected_errmsg)
