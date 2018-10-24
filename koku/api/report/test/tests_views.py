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
"""Test the Report views."""
from unittest.mock import patch

from django.http import HttpRequest, QueryDict
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.test import APIClient
from rest_framework_csv.renderers import CSVRenderer

from api.iam.serializers import UserSerializer
from api.iam.test.iam_test_case import IamTestCase
from api.models import User
from api.report.aws.queries import AWSReportQueryHandler
from api.report.aws.serializers import QueryParamSerializer
from api.report.view import (_convert_units,
                             _fill_in_missing_units,
                             _find_unit,
                             _generic_report,
                             process_query_parameters)
from api.utils import UnitConverter


class ReportViewTest(IamTestCase):
    """Tests the report view."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        serializer = UserSerializer(data=self.user_data, context=self.request_context)
        if serializer.is_valid(raise_exception=True):
            serializer.save()

        self.report = {
            'group_by': {
                'account': ['*']
            },
            'filter': {
                'resolution': 'monthly',
                'time_scope_value': -1,
                'time_scope_units': 'month',
                'resource_scope': []
            },
            'data': [
                {
                    'date': '2018-07',
                    'accounts': [
                        {
                            'account': '4418636104713',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'account': '4418636104713',
                                    'total': 1826.74238146924
                                }
                            ]
                        },
                        {
                            'account': '8577742690384',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'account': '8577742690384',
                                    'total': 1137.74036198065
                                }
                            ]
                        },
                        {
                            'account': '3474227945050',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'account': '3474227945050',
                                    'total': 1045.80659412797
                                }
                            ]
                        },
                        {
                            'account': '7249815104968',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'account': '7249815104968',
                                    'total': 807.326470618818
                                }
                            ]
                        },
                        {
                            'account': '9420673783214',
                            'values': [
                                {
                                    'date': '2018-07',
                                    'units': 'GB-Mo',
                                    'account': '9420673783214',
                                    'total': 658.306642830709
                                }
                            ]
                        }
                    ]
                }
            ],
            'total': {
                'value': 5475.922451027388,
                'units': 'GB-Mo'
            }
        }

    def test_get_costs_customer_owner(self):
        """Test costs reports runs with a customer owner."""
        url = reverse('reports-costs')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_instance_customer_owner(self):
        """Test inventory instance reports runs with a customer owner."""
        url = reverse('reports-instance-type')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_get_storage_customer_owner(self):
        """Test inventory storage reports runs with a customer owner."""
        url = reverse('reports-storage')
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        json_result = response.json()
        self.assertIsNotNone(json_result.get('data'))
        self.assertIsInstance(json_result.get('data'), list)
        self.assertTrue(len(json_result.get('data')) > 0)

    def test_process_query_parameters(self):
        """Test processing of valid parameters."""
        qs = 'group_by%5Baccount%5D=account1&filter%5Bresolution%5D=daily'
        valid, query_dict = process_query_parameters(qs, QueryParamSerializer)
        self.assertTrue(valid)
        self.assertEqual(query_dict.get('group_by'), {'account': ['account1']})
        self.assertEqual(query_dict.get('filter'), {'resolution': 'daily'})

    def test_process_query_parameters_invalid(self):
        """Test processing of invalid parameters."""
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        valid, _ = process_query_parameters(qs, QueryParamSerializer)
        self.assertFalse(valid)

    def test_get_costs_invalid_query_param(self):
        """Test costs reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 400)

    def test_get_instance_usage_invalid_query_param(self):
        """Test instance usage reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-instance-type') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 400)

    def test_get_storage_usage_invalid_query_param(self):
        """Test storage usage reports runs with an invalid query param."""
        qs = 'group_by%5Binvalid%5D=account1&filter%5Bresolution%5D=daily'
        url = reverse('reports-storage') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 400)

    def test_get_costs_csv(self):
        """Test CSV output of costs reports."""
        url = reverse('reports-costs')
        client = APIClient(HTTP_ACCEPT='text/csv')

        response = client.get(url, **self.headers)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_instance_csv(self):
        """Test CSV output of inventory instance reports."""
        url = reverse('reports-instance-type')
        client = APIClient(HTTP_ACCEPT='text/csv')
        response = client.get(url, content_type='text/csv', **self.headers)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_get_storage_csv(self):
        """Test CSV output of inventory storage reports."""
        url = reverse('reports-storage')
        client = APIClient(HTTP_ACCEPT='text/csv')
        response = client.get(url, content_type='text/csv', **self.headers)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.accepted_media_type, 'text/csv')
        self.assertIsInstance(response.accepted_renderer, CSVRenderer)

    def test_convert_units_success(self):
        """Test unit conversion succeeds."""
        converter = UnitConverter()
        to_unit = 'byte'
        expected_unit = f'{to_unit}-Mo'
        report_total = self.report.get('total', {}).get('value')

        result = _convert_units(converter, self.report, to_unit)
        result_unit = result.get('total', {}).get('units')
        result_total = result.get('total', {}).get('value')

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1E9, result_total)

    def test_convert_units_list(self):
        """Test that the list check is hit."""
        converter = UnitConverter()
        to_unit = 'byte'
        expected_unit = f'{to_unit}-Mo'
        report_total = self.report.get('total', {}).get('value')

        report = [self.report]
        result = _convert_units(converter, report, to_unit)
        result_unit = result[0].get('total', {}).get('units')
        result_total = result[0].get('total', {}).get('value')

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1E9, result_total)

    def test_convert_units_total_not_dict(self):
        """Test that the total not dict block is hit."""
        converter = UnitConverter()
        to_unit = 'byte'
        expected_unit = f'{to_unit}-Mo'

        report = self.report['data'][0]['accounts'][0]['values'][0]
        report_total = report.get('total')
        result = _convert_units(converter, report, to_unit)
        result_unit = result.get('units')
        result_total = result.get('total')

        self.assertEqual(expected_unit, result_unit)
        self.assertEqual(report_total * 1E9, result_total)

    @patch('api.report.aws.queries.AWSReportQueryHandler')
    def test_generic_report_with_units_success(self, mock_handler):
        """Test unit conversion succeeds in generic report."""
        mock_handler.return_value.execute_query.return_value = self.report
        params = {
            'group_by[account]': '*',
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'units': 'byte'
        }
        user = User.objects.get(
            username=self.user_data['username']
        )

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        extras = {'report_type': 'costs'}
        response = _generic_report(request, QueryParamSerializer, AWSReportQueryHandler, **extras)
        self.assertIsInstance(response, Response)

    @patch('api.report.aws.queries.AWSReportQueryHandler')
    def test_generic_report_with_units_fails_well(self, mock_handler):
        """Test that validation error is thrown for bad unit conversion."""
        mock_handler.return_value.execute_query.return_value = self.report
        # The 'bad' unit here is that the report is in GB-Mo, and can't
        # convert to seconds
        params = {
            'group_by[account]': '*',
            'filter[resolution]': 'monthly',
            'filter[time_scope_value]': '-1',
            'filter[time_scope_units]': 'month',
            'units': 'second'
        }

        user = User.objects.get(
            username=self.user_data['username']
        )

        django_request = HttpRequest()
        qd = QueryDict(mutable=True)
        qd.update(params)
        django_request.GET = qd
        request = Request(django_request)
        request.user = user

        with self.assertRaises(ValidationError):
            extras = {'report_type': 'costs'}
            _generic_report(request, QueryParamSerializer, mock_handler, **extras)

    def test_find_unit_list(self):
        """Test that the correct unit is returned."""
        expected_unit = 'Hrs'
        data = [
            {'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit, 'instance_type': 't2.small', 'total': 17.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit, 'instance_type': 't2.micro', 'total': 1.0, 'count': 0}
        ]

        result_unit = _find_unit()(data)
        self.assertEqual(expected_unit, result_unit)

    def test_find_unit_dict(self):
        """Test that the correct unit is returned for a dictionary."""
        data = {'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0},

        result_unit = _find_unit()(data)
        self.assertIsNone(result_unit)

    def test_fill_in_missing_units_list(self):
        """Test that missing units are filled in."""
        expected_unit = 'Hrs'
        data = [
            {'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit, 'instance_type': 't2.small', 'total': 17.0, 'count': 0},
            {'date': '2018-07-22', 'units': expected_unit, 'instance_type': 't2.micro', 'total': 1.0, 'count': 0}
        ]

        unit = _find_unit()(data)

        result = _fill_in_missing_units(unit)(data)

        for entry in result:
            self.assertEqual(entry.get('units'), expected_unit)

    def test_fill_in_missing_units_dict(self):
        """Test that missing units are filled in for a dictionary."""
        expected_unit = 'Hrs'
        data = {'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0}

        result = _fill_in_missing_units(expected_unit)(data)

        self.assertEqual(result.get('units'), expected_unit)

    def test_execute_query_w_delta_true(self):
        """Test that delta=True returns deltas."""
        qs = 'delta=True'
        url = reverse('reports-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

        qs = 'delta=False'
        url = reverse('reports-costs') + '?' + qs
        response = client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        bad_delta = 'Invalid'
        expected = f'"{bad_delta}" is not a valid boolean.'
        qs = f'group_by[account]=*&filter[limit]=2&delta={bad_delta}'
        url = reverse('reports-costs') + '?' + qs
        client = APIClient()
        response = client.get(url, **self.headers)
        result = str(response.data.get('delta')[0])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(result, expected)
