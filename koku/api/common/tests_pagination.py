#
# Copyright 2018 Red Hat, Inc.
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
"""Test the API pagination module."""
from unittest.mock import Mock

from django.test import TestCase

from .pagination import HTTP_REFERER, StandardResultsSetPagination


class PaginationTest(TestCase):
    """Tests against the pagination functions."""

    def test_link_rewrite(self):
        """Test the link rewrite."""
        request = Mock()
        request.META = {HTTP_REFERER: 'https://api.koku.com/'}
        link = 'http://localhost:8000/api/v1/providers/?page=2'
        expected = 'https://api.koku.com/api/v1/providers/?page=2'
        result = StandardResultsSetPagination.link_rewrite(request, link)
        self.assertEqual(expected, result)

    def test_link_now_rewrite(self):
        """Test the no link rewrite."""
        request = Mock()
        request.META = {}
        link = 'http://localhost:8000/api/v1/providers/?page=2'
        result = StandardResultsSetPagination.link_rewrite(request, link)
        self.assertEqual(link, result)
