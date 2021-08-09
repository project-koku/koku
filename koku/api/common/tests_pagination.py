#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the API pagination module."""
import random
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from rest_framework.response import Response

from .pagination import PATH_INFO
from .pagination import ReportPagination
from .pagination import ReportRankedPagination
from .pagination import StandardResultsSetPagination


class StandardResultsSetPaginationTest(TestCase):
    """Tests against the standard pagination functions."""

    def test_link_rewrite(self):
        """Test the link rewrite."""
        request = Mock()
        request.META = {PATH_INFO: "/v1/sources/"}
        link = "http://localhost:8000/v1/sources/?offset=20"
        expected = "/v1/sources/?offset=20"
        result = StandardResultsSetPagination.link_rewrite(request, link)
        self.assertEqual(expected, result)

    def test_link_rewrite_err(self):
        """Test the link rewrite."""
        request = Mock()
        request.META = {PATH_INFO: "https://localhost:8000/sources/"}
        link = "http://localhost:8000/sources/?offset=20"
        result = StandardResultsSetPagination.link_rewrite(request, link)
        self.assertEqual(link, result)

    def test_link_no_rewrite(self):
        """Test the no link rewrite."""
        request = Mock()
        request.META = {}
        link = "http://localhost:8000/api/v1/sources/?offset=20"
        result = StandardResultsSetPagination.link_rewrite(request, link)
        self.assertEqual(link, result)

    @patch("api.common.pagination.LimitOffsetPagination.get_next_link", return_value=None)
    def test_get_next_link_none(self, mock_super):
        """Test the get next link method when super returns none."""
        paginator = StandardResultsSetPagination()
        link = paginator.get_next_link()
        self.assertIsNone(link)

    @patch("api.common.pagination.LimitOffsetPagination.get_previous_link", return_value=None)
    def test_get_previous_link_none(self, mock_super):
        """Test the get previous link method when super returns none."""
        paginator = StandardResultsSetPagination()
        link = paginator.get_previous_link()
        self.assertIsNone(link)

    @patch("api.common.pagination.LimitOffsetPagination.get_next_link")
    def test_get_next_link_value(self, mock_super):
        """Test the get next link method when super returns a value."""
        expected = "http://localhost:8000/api/v1/sources/?offset=20"
        mock_super.return_value = expected
        paginator = StandardResultsSetPagination()
        paginator.request = Mock
        paginator.request.META = {}
        link = paginator.get_next_link()
        self.assertEqual(link, expected)

    @patch("api.common.pagination.LimitOffsetPagination.get_previous_link")
    def test_get_previous_link_value(self, mock_super):
        """Test the get previous link method when super returns a value."""
        expected = "http://localhost:8000/api/v1/sources/?offset=20"
        mock_super.return_value = expected
        paginator = StandardResultsSetPagination()
        paginator.request = Mock
        paginator.request.META = {}
        link = paginator.get_previous_link()
        self.assertEqual(link, expected)


class ReportPaginationTest(TestCase):
    """Tests for report API pagination."""

    def setUp(self):
        """Set up each test case."""
        self.paginator = ReportPagination()
        self.paginator.request = Mock
        self.paginator.request.META = {}
        self.paginator.request.query_params = {}

        self.data = {"total": {}, "data": [{"usage": 1, "cost": 2}, {"usage": 2, "cost": 4}]}

    def test_get_count(self):
        """Test that count is returned properly."""
        expected = len(self.data.get("data", []))
        self.assertEqual(self.paginator.get_count(self.data), expected)

    def test_paginate_queryset(self):
        """Test that the queryset is paginated properly."""
        expected_limit = 1
        self.paginator.request.query_params = {"limit": expected_limit}
        data = self.paginator.paginate_queryset(self.data, self.paginator.request)

        self.assertEqual(len(data.get("data", [])), expected_limit)

    def test_paginate_queryset_nolimit(self):
        """Test that the queryset is paginated properly."""
        limit = 0
        expected = len(self.data.get("data", []))

        self.paginator.request.query_params = {"limit": limit}
        data = self.paginator.paginate_queryset(self.data, self.paginator.request)

        self.assertEqual(len(data.get("data", [])), expected)

    def test_paginate_queryset_high_offset(self):
        """Test that the queryset is paginated properly."""
        limit = 1
        offset = 100
        self.paginator.request.query_params = {"limit": limit, "offset": offset}
        data = self.paginator.paginate_queryset(self.data, self.paginator.request)

        self.assertEqual(len(data.get("data", [])), 0)

    @patch("api.common.pagination.ReportPagination.get_last_link")
    @patch("api.common.pagination.ReportPagination.get_previous_link")
    @patch("api.common.pagination.ReportPagination.get_next_link")
    @patch("api.common.pagination.ReportPagination.get_first_link")
    def test_get_paginated_response(self, mock_first, mock_next, mock_prev, mock_last):
        """Test that the response object has the right keys."""
        data = self.paginator.paginate_queryset(self.data, self.paginator.request)
        response = self.paginator.get_paginated_response(data)
        response_data = response.data
        meta = response_data.get("meta", {})
        links = response_data.get("links", {})

        self.assertIsInstance(response, Response)
        self.assertIn("meta", response_data)
        self.assertIn("links", response_data)
        self.assertIn("data", response_data)
        self.assertIn("count", meta)
        self.assertIn("total", meta)
        self.assertIn("first", links)
        self.assertIn("next", links)
        self.assertIn("previous", links)
        self.assertIn("last", links)


class ReportRankedPaginationTest(TestCase):
    """Tests for ranked report API pagination."""

    def setUp(self):
        """Set up each test case."""
        self.paginator = ReportRankedPagination()
        self.paginator.count = random.randint(1, 10)
        self.paginator.request = Mock
        self.paginator.request.META = {}
        self.paginator.request.query_params = {}

        self.data = {"total": {}, "data": [{"usage": 1, "cost": 2}, {"usage": 2, "cost": 4}]}

    def test_get_count(self):
        """Test that count is returned properly."""
        expected = self.paginator.count
        self.assertEqual(self.paginator.get_count(self.data), expected)

    def test_paginate_queryset(self):
        """Test that the queryset is unaltered."""
        data = self.paginator.paginate_queryset(self.data, self.paginator.request)
        self.assertEqual(data.get("data", []), self.data.get("data", []))
