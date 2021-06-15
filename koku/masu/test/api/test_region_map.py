#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the region map endpoint."""
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings

TEST_HTML = "./koku/masu/test/data/test_region_page.html"


class MockResponse:
    """A fake requests.Response object."""

    status_code = None
    text = None

    def __init__(self, data, status):
        """Initialize a mock response."""
        self.status_code = status
        self.text = str(data)


@override_settings(ROOT_URLCONF="masu.urls")
class RegionMapAPIViewTest(TestCase):
    """Test Cases for the Region Map API."""

    @classmethod
    def setUpClass(cls):
        """Set up test class with shared objects."""
        with open(TEST_HTML) as page:
            cls.test_data = page.read()

    @patch("koku.middleware.MASU", return_value=True)
    @patch("masu.database.reporting_common_db_accessor.ReportingCommonDBAccessor", autospec=True)
    @patch("masu.util.aws.region_map.requests.get")
    def skip_test_update_region_map(self, mock_response, mock_accessor, _):
        """Test the region map endpoint."""
        mock_response.return_value = MockResponse(self.test_data, 200)

        response = self.client.get("/api/v1/regionmap/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "true\n")
