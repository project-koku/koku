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
"""Test the QueryParameters."""

import random
from unittest.mock import Mock, patch

from django.test import TestCase
from faker import Faker

from api.query_params import QueryParameters

class QueryParametersTests(TestCase):
    """Unit tests for QueryParameters."""

    def test_has_filter_no_filter(self):
        """Test the default filter query parameters."""
        params = Mock(spec=QueryParameters, return_value=None,
                      tenant=self.tenant, report_type='costs')
        handler = AWSReportQueryHandler(params)
        self.assertTrue(handler.check_query_params('filter', 'time_scope_units'))
        self.assertTrue(handler.check_query_params('filter', 'time_scope_value'))
        self.assertTrue(handler.check_query_params('filter', 'resolution'))
        self.assertEqual(handler.query_parameters.get('filter').get('time_scope_units'), 'day')
        self.assertEqual(handler.query_parameters.get('filter').get('time_scope_value'), '-10')
        self.assertEqual(handler.query_parameters.get('filter').get('resolution'), 'daily')

    def test_has_filter_with_filter(self):
        """Test the has_filter method with filter in the query params."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertIsNotNone(handler.check_query_params('filter', 'time_scope_value'))

    def test_get_group_by_no_data(self):
        """Test the get_group_by_data method with no data in the query params."""
        handler = AWSReportQueryHandler({}, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertFalse(handler.get_query_param_data('group_by', 'service'))

    def test_get_group_by_with_service_list(self):
        """Test the get_group_by_data method with no data in the query params."""
        expected = ['a', 'b']
        query_string = '?group_by[service]=a&group_by[service]=b'
        handler = AWSReportQueryHandler({'group_by':
                                        {'service': expected}},
                                        query_string,
                                        self.tenant,
                                        **{'report_type': 'costs'})
        service = handler.get_query_param_data('group_by', 'service')
        self.assertEqual(expected, service)

    def test_get_resolution_empty_default(self):
        """Test get_resolution returns default when query params are empty."""
        query_params = {}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.resolution, 'daily')

