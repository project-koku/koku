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

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse


@override_settings(ROOT_URLCONF="masu.urls")
class crawlAccountHierarchyTest(TestCase):
    """Test Cases for the crawl_account_hierarchy endpoint."""

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.api.crawl_account_hierarchy.crawl_hierarchy")
    def test_get_crawl_account_hierarchy(self, mock_update, _):
        """Test the GET report_data endpoint."""
        response = self.client.get(reverse("crawl_account_hierarchy"))
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Crawl account hierarchy Task ID", body)
        mock_update.delay.assert_called_with()
