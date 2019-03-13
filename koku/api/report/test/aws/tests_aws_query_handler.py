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
"""Test the AWS Query Handler."""
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from api.report.aws.aws_query_handler import _update_query_parameters


class AwsQueryHandlerFunctionTest(TestCase):
    """Test the AWS Query Handler functions."""

    def test_update_query_parameters_with_wildcard(self):
        """Test wildcard doesn't update query parameters."""
        query_parameters = {
            'group_by': {'account': ['*'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['*']}
        }
        out = _update_query_parameters(query_parameters, access)
        self.assertEqual(query_parameters, out)

    def test_update_query_parameters_replace_wildcard(self):
        """Test that a group by account wildcard is replaced with only the subset of accounts."""
        query_parameters = {
            'group_by': {'account': ['*'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = _update_query_parameters(query_parameters, access)
        expected = {
            'group_by': {'account': ['account1', 'account2'], 'region': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_gb_filtered_intersection(self):
        """Test that a group by account filtered list is replaced with only the intersection of accounts."""
        query_parameters = {
            'group_by': {'account': ['account1', 'account5'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = _update_query_parameters(query_parameters, access)
        expected = {
            'group_by': {'account': ['account1'], 'region': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_empty_intersection(self):
        """Test that a group by account filtered list causes 403 when empty intersection of accounts."""
        query_parameters = {
            'group_by': {'account': ['account1', 'account5'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account4', 'account2']}
        }
        with self.assertRaises(PermissionDenied):
            _update_query_parameters(query_parameters, access)

    def test_update_query_parameters_add_account_filter(self):
        """Test that if no group_by or filter is present a filter of accounts is added."""
        query_parameters = {
            'filter': {'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = _update_query_parameters(query_parameters, access)
        expected = {
            'filter': {'account': ['account1', 'account2'], 'region': ['*']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_add_account_filter_obj(self):
        """Test that if no group_by or filter is present a filter of accounts is added."""
        query_parameters = {}
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = _update_query_parameters(query_parameters, access)
        expected = {
            'filter': {'account': ['account1', 'account2']}
        }
        self.assertEqual(expected, out)

    def test_update_query_parameters_filtered_intersection(self):
        """Test that a filter by account filtered list is replaced with only the intersection of accounts."""
        query_parameters = {
            'filter': {'account': ['account1', 'account5'], 'region': ['*']}
        }
        access = {
            'aws.account': {'read': ['account1', 'account2']}
        }
        out = _update_query_parameters(query_parameters, access)
        expected = {
            'filter': {'account': ['account1'], 'region': ['*']}
        }
        self.assertEqual(expected, out)
