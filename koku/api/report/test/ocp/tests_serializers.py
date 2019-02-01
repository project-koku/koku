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
                                        OCPChargeQueryParamSerializer,
                                        OCPInventoryQueryParamSerializer,
                                        OCPQueryParamSerializer,
                                        OrderBySerializer)


class OCPFilterSerializerTest(TestCase):
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

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ['valid_tag']
        query_params = {'valid_tag': 'value'}
        serializer = FilterSerializer(data=query_params,
                                      tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ['valid_tag']
        query_params = {'bad_tag': 'value'}
        serializer = FilterSerializer(data=query_params,
                                      tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPGroupBySerializerTest(TestCase):
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

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ['valid_tag']
        query_params = {'valid_tag': '*'}
        serializer = GroupBySerializer(data=query_params,
                                       tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ['valid_tag']
        query_params = {'bad_tag': '*'}
        serializer = GroupBySerializer(data=query_params,
                                       tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPOrderBySerializerTest(TestCase):
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

    def test_tag_keys_dynamic_field_validation_success(self):
        """Test that tag keys are validated as fields."""
        tag_keys = ['valid_tag']
        query_params = {'filter': {'valid_tag': 'value'}}
        serializer = OCPQueryParamSerializer(data=query_params,
                                             tag_keys=tag_keys)
        self.assertTrue(serializer.is_valid())

    def test_tag_keys_dynamic_field_validation_failure(self):
        """Test that invalid tag keys are not valid fields."""
        tag_keys = ['valid_tag']
        query_params = {'filter': {'bad_tag': 'value'}}
        serializer = OCPQueryParamSerializer(data=query_params,
                                             tag_keys=tag_keys)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPInventoryQueryParamSerializerTest(TestCase):
    """Tests for the handling inventory query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of an inventory query params successfully."""
        query_params = {'group_by': {'project': ['project1']},
                        'order_by': {'usage': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        }
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_order_by(self):
        """Test parse of inventory query params for invalid fields."""
        # Pass requests instead of request
        query_params = {'group_by': {'account': ['account1']},
                        'order_by': {'requests': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        'invalid': 'param'
                        }
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_delta_success(self):
        """Test that a proper delta value is serialized."""
        query_params = {'delta': 'charge'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {'delta': 'usage'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {'delta': 'request'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_delta_failure(self):
        """Test that a bad delta value is not serialized."""
        query_params = {'delta': 'bad_delta'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_current_month_delta_success(self):
        """Test that a proper current month delta value is serialized."""
        query_params = {'delta': 'usage__request'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {'delta': 'usage__capacity'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

        query_params = {'delta': 'request__capacity'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_current_month_delta_failure(self):
        """Test that a bad current month delta value is not serialized."""
        query_params = {'delta': 'bad__delta'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

        query_params = {'delta': 'usage__request__capacity'}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_order_by_delta_with_delta(self):
        """Test that order_by[delta] works with a delta param."""
        query_params = {
            'delta': 'usage__request',
            'order_by': {'delta': 'asc'}
        }
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_order_by_delta_without_delta(self):
        """Test that order_by[delta] does not work without a delta param."""
        query_params = {'order_by': {'delta': 'asc'}}
        serializer = OCPInventoryQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)


class OCPChargeQueryParamSerializerTest(TestCase):
    """Tests for the handling charge query parameter parsing serializer."""

    def test_parse_query_params_success(self):
        """Test parse of a charge query params successfully."""
        query_params = {'group_by': {'project': ['project1']},
                        'order_by': {'charge': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        }
        serializer = OCPChargeQueryParamSerializer(data=query_params)
        self.assertTrue(serializer.is_valid())

    def test_query_params_invalid_order_by_request(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {'group_by': {'account': ['account1']},
                        'order_by': {'request': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        'invalid': 'param'
                        }
        serializer = OCPChargeQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)

    def test_query_params_invalid_order_by_usage(self):
        """Test parse of charge query params for invalid fields."""
        # Charge can't order by request or usage
        query_params = {'group_by': {'account': ['account1']},
                        'order_by': {'usage': 'asc'},
                        'filter': {'resolution': 'daily',
                                   'time_scope_value': '-10',
                                   'time_scope_units': 'day',
                                   'resource_scope': []},
                        'invalid': 'param'
                        }
        serializer = OCPChargeQueryParamSerializer(data=query_params)
        with self.assertRaises(serializers.ValidationError):
            serializer.is_valid(raise_exception=True)
