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
"""Test the OCP on AWS Report serializers."""
from unittest import TestCase

from api.report.ocp_aws.serializers import (OCPAWSFilterSerializer,
                                            OCPAWSGroupBySerializer,
                                            OCPAWSOrderBySerializer,
                                            OCPAWSQueryParamSerializer)


class OCPAWSFilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {'resolution': 'daily',
                         'time_scope_value': '-10',
                         'time_scope_units': 'day',
                         'resource_scope': []}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_project(self):
        """Test filter by project."""
        filter_params = {'project': ['*']}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_cluster(self):
        """Test filter by cluster."""
        filter_params = {'cluster': ['*']}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_node(self):
        """Test filter by node."""
        filter_params = {'node': ['*']}
        serializer = OCPAWSFilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_all_filter_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAWSFilterSerializer._opfields:
            field = 'and:' + field
            filter_param = {field: ['1', '2']}
            serializer = OCPAWSFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAWSFilterSerializer._opfields:
            field = 'or:' + field
            filter_param = {field: ['1', '2']}
            serializer = OCPAWSFilterSerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPAWSGroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_project(self):
        """Test group by project."""
        group_params = {'project': ['*']}
        serializer = OCPAWSGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_cluster(self):
        """Test group by cluster."""
        group_params = {'cluster': ['*']}
        serializer = OCPAWSGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_node(self):
        """Test group by node."""
        group_params = {'node': ['*']}
        serializer = OCPAWSGroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_all_group_by_op_fields(self):
        """Test that the allowed fields pass."""
        for field in OCPAWSGroupBySerializer._opfields:
            field = 'and:' + field
            filter_param = {field: ['1', '2']}
            serializer = OCPAWSGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())
        for field in OCPAWSGroupBySerializer._opfields:
            field = 'or:' + field
            filter_param = {field: ['1', '2']}
            serializer = OCPAWSGroupBySerializer(data=filter_param)
            self.assertTrue(serializer.is_valid())


class OCPAWSOrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_order_by_project(self):
        """Test order by project."""
        order_params = {'project': 'asc'}
        serializer = OCPAWSOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_cluster(self):
        """Test order by cluster."""
        order_params = {'cluster': 'asc'}
        serializer = OCPAWSOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_node(self):
        """Test order by node."""
        order_params = {'node': 'asc'}
        serializer = OCPAWSOrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())


class OCPAWSQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {'group_by': {'project': ['account1']},
                        'order_by': {'project': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        'units': 'byte'
                        }
        serializer = OCPAWSQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())
