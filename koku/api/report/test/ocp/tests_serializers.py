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
"""Test the Report serializers."""
from unittest import TestCase

from rest_framework import serializers

from api.report.ocp.serializers import (FilterSerializer,
                                        GroupBySerializer,
                                        OCPQueryParamSerializer,
                                        OrderBySerializer)


class FilterSerializerTest(TestCase):
    """Tests for the filter serializer."""

    def test_parse_filter_params_success(self):
        """Test parse of a filter param successfully."""
        filter_params = {'resolution': 'daily',
                         'time_scope_value': '-10',
                         'time_scope_units': 'day',
                         'resource_scope': []}
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_filter_params_no_time(self):
        """Test parse of a filter param no time filter."""
        filter_params = {'resource_scope': ['S3']}
        serializer = FilterSerializer(data=filter_params)
        self.assertTrue(serializer.is_valid())

    def test_filter_params_invalid_fields(self):
        """Test parse of filter params for invalid fields."""
        filter_params = {'resolution': 'daily',
                         'time_scope_value': '-10',
                         'time_scope_units': 'day',
                         'resource_scope': [],
                         'invalid': 'param'}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_daily(self):
        """Test parse of filter params for invalid daily time_scope_units."""
        filter_params = {'resolution': 'daily',
                         'time_scope_value': '-1',
                         'time_scope_units': 'day'}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_time_scope_monthly(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {'resolution': 'monthly',
                         'time_scope_value': '-10',
                         'time_scope_units': 'month'}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit(self):
        """Test parse of filter params for invalid month time_scope_units."""
        filter_params = {'resolution': 'monthly',
                         'time_scope_value': '-1',
                         'time_scope_units': 'month',
                         'limit': 'invalid'}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_filter_params_invalid_limit_time_scope_resolution(self):
        """Test parse of filter params for invalid resolution time_scope_units."""
        filter_params = {'resolution': 'monthly',
                         'time_scope_value': '-10',
                         'time_scope_units': 'day'}
        serializer = FilterSerializer(data=filter_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class GroupBySerializerTest(TestCase):
    """Tests for the group_by serializer."""

    def test_parse_group_by_params_success(self):
        """Test parse of a group_by param successfully."""
        group_params = {'cluster': ['cluster1']}
        serializer = GroupBySerializer(data=group_params)
        self.assertTrue(serializer.is_valid())

    def test_group_by_params_invalid_fields(self):
        """Test parse of group_by params for invalid fields."""
        group_params = {'account': ['account1'],
                        'invalid': 'param'}
        serializer = GroupBySerializer(data=group_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_group_by_params_string_list_fields(self):
        """Test group_by params for handling string to list fields."""
        group_params = {'node': 'localhost'}
        serializer = GroupBySerializer(data=group_params)
        validation = serializer.is_valid()
        self.assertTrue(validation)
        node_result = serializer.data.get('node')
        self.assertIsInstance(node_result, list)


class OrderBySerializerTest(TestCase):
    """Tests for the order_by serializer."""

    def test_parse_order_by_params_success(self):
        """Test parse of a order_by param successfully."""
        order_params = {'project': 'asc'}
        serializer = OrderBySerializer(data=order_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_params_invalid_fields(self):
        """Test parse of order_by params for invalid fields."""
        order_params = {'cost': 'asc',
                        'invalid': 'param'
                        }
        serializer = OrderBySerializer(data=order_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPQueryParamSerializerTest(TestCase):
    """Tests for the handling query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a query params successfully."""
        query_params = {'group_by': {'project': ['project1']},
                        'order_by': {'cluster': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        }
        serializer = OCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_fields(self):
        """Test parse of query params for invalid fields."""
        query_params = {'group_by': {'account': ['account1']},
                        'order_by': {'cost': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        'invalid': 'param'
                        }
        serializer = OCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_nested_fields(self):
        """Test parse of query params for invalid nested_fields."""
        query_params = {'group_by': {'invalid': ['invalid']},
                        'order_by': {'cost': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []}
                        }
        serializer = OCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_parse_units(self):
        """Test pass while parsing units query params."""
        query_params = {'units': 'bytes'}
        serializer = OCPQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_parse_units_failure(self):
        """Test failure while parsing units query params."""
        query_params = {'units': 'bites'}
        serializer = OCPQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
